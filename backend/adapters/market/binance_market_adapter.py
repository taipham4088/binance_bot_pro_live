import asyncio
import inspect
import threading
import pandas as pd

from backend.ports.market_port import MarketPort
from backend.live.feed.binance_ws_client import BinanceWSClient
from backend.live.market.live_feature_engine import LiveFeatureEngine
from backend.live.market.binance_history_loader import BinanceHistoryLoader


def _log_adapter_create_source(session_id: str | None, symbol: str) -> None:
    st = inspect.stack()
    fr = st[2] if len(st) > 2 else st[-1]
    print(
        "[ADAPTER CREATE SOURCE]",
        f"file={fr.filename}",
        f"caller={fr.function}:{fr.lineno}",
        f"session={session_id!r}",
        f"symbol={symbol!r}",
    )


class BinanceMarketAdapter(MarketPort):
    _history_cache_entry: dict[tuple[str, str], pd.DataFrame] = {}
    _history_cache_regime: dict[tuple[str, str], pd.DataFrame] = {}

    def __init__(
        self,
        symbol: str,
        entry_interval: str,
        regime_interval: str,
        session_id: str | None = None,
    ):
        self.symbol = symbol
        self.entry_interval = (entry_interval or "5m").strip().lower()
        self.regime_interval = (regime_interval or "1h").strip().lower()
        # WebSocket stream follows entry (signal) timeframe
        self.tf = self.entry_interval

        self.df = pd.DataFrame()
        self.callbacks = []
        # When False, _on_ws_candle ignores candles (stops FEATURE CHECK during teardown).
        self._ingesting = True

        _log_adapter_create_source(session_id, symbol)

        self.feature_engine = LiveFeatureEngine(
            min_bars=300,
            session_id=session_id,
            entry_interval=self.entry_interval,
            regime_interval=self.regime_interval,
        )

        print(
            "[ADAPTER CREATE]",
            f"adapter_id={id(self)}",
            f"feature_engine_id={id(self.feature_engine)}",
            f"symbol={symbol!r}",
            f"entry_interval={self.entry_interval!r}",
            f"regime_interval={self.regime_interval!r}",
        )

        print("[LIVE] loading history...")
        ek = (symbol, self.entry_interval)
        rk = (symbol, self.regime_interval)
        cached_entry = BinanceMarketAdapter._history_cache_entry.get(ek)
        cached_regime = BinanceMarketAdapter._history_cache_regime.get(rk)

        if (
            cached_entry is None
            or cached_regime is None
            or cached_entry.empty
            or cached_regime.empty
        ):
            hist_df_entry = BinanceHistoryLoader.load(
                symbol=symbol,
                interval=self.entry_interval,
                limit=3000,
            )
            hist_df_regime = BinanceHistoryLoader.load(
                symbol=symbol,
                interval=self.regime_interval,
                limit=500,
            )
        else:
            latest_entry = BinanceHistoryLoader.load(
                symbol=symbol,
                interval=self.entry_interval,
                limit=5,
            )
            latest_regime = BinanceHistoryLoader.load(
                symbol=symbol,
                interval=self.regime_interval,
                limit=3,
            )
            hist_df_entry = pd.concat([cached_entry, latest_entry], ignore_index=True)
            hist_df_regime = pd.concat([cached_regime, latest_regime], ignore_index=True)

        hist_df_entry["time"] = pd.to_datetime(hist_df_entry["time"])
        hist_df_regime["time"] = pd.to_datetime(hist_df_regime["time"])

        hist_df_entry = hist_df_entry.sort_values("time")
        hist_df_regime = hist_df_regime.sort_values("time")
        hist_df_entry = (
            hist_df_entry.drop_duplicates(subset=["time"], keep="last")
            .tail(3000)
            .reset_index(drop=True)
        )
        hist_df_regime = (
            hist_df_regime.drop_duplicates(subset=["time"], keep="last")
            .tail(500)
            .reset_index(drop=True)
        )

        BinanceMarketAdapter._history_cache_entry[ek] = hist_df_entry.copy(deep=True)
        BinanceMarketAdapter._history_cache_regime[rk] = hist_df_regime.copy(deep=True)

        self.feature_engine.bootstrap(hist_df_entry, hist_df_regime)
        self.df = self.feature_engine.df_entry

        print("[LIVE] history loaded:", len(self.df), "bars")
        print("REGIME HISTORY SIZE:", self.regime_interval, len(hist_df_regime))
        print(hist_df_regime.tail())

        self.client = BinanceWSClient(
            symbol=symbol,
            timeframe=self.entry_interval,
            on_candle=self._on_ws_candle,
        )

        self.thread = threading.Thread(
            target=self._start_ws,
            daemon=True,
        )

    def get_latest_candle(self, symbol=None, tf=None):
        if self.df is None or len(self.df) == 0:
            return None, None

        required_cols = [
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short",
            "range_high",
            "range_low",
        ]

        if not all(col in self.df.columns for col in required_cols):
            return None, None

        return len(self.df) - 1, self.df.iloc[-1]

    def subscribe_candle(self, callback):
        # Single subscriber per adapter: strategy switch / re-run must never stack callbacks.
        replaced = len(self.callbacks)
        self.callbacks.clear()
        self.callbacks.append(callback)
        print(
            "[SUBSCRIBE ADD]",
            f"adapter_id={id(self)}",
            f"count={len(self.callbacks)}",
            f"replaced_prior={replaced}",
            f"cb={callback!r}",
        )
        if not self.thread.is_alive():
            self.thread.start()

    def unsubscribe_candle(self, callback) -> None:
        """Remove one subscriber; no-op if absent."""
        try:
            self.callbacks.remove(callback)
        except ValueError:
            return
        print(
            "[SUBSCRIBE REMOVE]",
            f"adapter_id={id(self)}",
            f"count={len(self.callbacks)}",
        )

    def stop(self):
        self._ingesting = False
        n = len(self.callbacks)
        print(
            "[ADAPTER STOP]",
            f"adapter_id={id(self)}",
            f"callback_count_before={n}",
        )
        if getattr(self, "client", None):
            self.client.stop()
        th = getattr(self, "thread", None)
        if th is not None and th.is_alive():
            th.join(timeout=8.0)
        self.callbacks.clear()
        print(
            "[ADAPTER STOP]",
            f"adapter_id={id(self)}",
            "callbacks_cleared",
            "count=0",
        )

    def _start_ws(self):
        asyncio.run(self.client.connect())

    async def _on_ws_candle(self, candle: dict):
        if not getattr(self, "_ingesting", False):
            return

        row = {
            "time": pd.to_datetime(candle["time"], unit="s"),
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
            "volume": candle["volume"],
        }

        result = self.feature_engine.push_candle(row)

        if result is None:
            return

        i, last_row, df = result

        required_cols = [
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short",
            "range_high",
            "range_low",
        ]

        if not all(col in df.columns for col in required_cols):
            return

        self.df = df

        print(
            "ADAPTER CHECK:",
            last_row[["ema200", "close_1h", "valid_long", "valid_short"]],
        )

        for cb in list(self.callbacks):
            cb(i, last_row, df)
