import asyncio
import threading
import pandas as pd

from backend.ports.market_port import MarketPort
from backend.live.feed.binance_ws_client import BinanceWSClient
from backend.live.market.live_feature_engine import LiveFeatureEngine
from backend.live.market.binance_history_loader import BinanceHistoryLoader


class BinanceMarketAdapter(MarketPort):

    def __init__(self, symbol: str, timeframe: str):
        self.symbol = symbol
        self.tf = timeframe

        self.df = pd.DataFrame()
        self.callbacks = []

        # ===== live feature engine =====
        self.feature_engine = LiveFeatureEngine(min_bars=300)

        # ===== history bootstrap =====
        print("[LIVE] loading history...")

        hist_df_5m = BinanceHistoryLoader.load(
            symbol=symbol,
            interval=timeframe,
            limit=3000
        )

        hist_df_1h = BinanceHistoryLoader.load(
            symbol=symbol,
            interval="1h",
            limit=500
        )
        # chuẩn hóa time
        hist_df_5m["time"] = pd.to_datetime(hist_df_5m["time"])
        hist_df_1h["time"] = pd.to_datetime(hist_df_1h["time"])

        hist_df_5m = hist_df_5m.sort_values("time")
        hist_df_1h = hist_df_1h.sort_values("time")

        self.feature_engine.bootstrap(hist_df_5m, hist_df_1h)
        self.df = self.feature_engine.df_5m

        print("[LIVE] history loaded:", len(self.df), "bars")
        print("H1 HISTORY SIZE:", len(hist_df_1h))
        print(hist_df_1h.tail())

        # ===== websocket client =====
        self.client = BinanceWSClient(
            symbol=symbol,
            timeframe=timeframe,
            on_candle=self._on_ws_candle
        )

        self.thread = threading.Thread(
            target=self._start_ws,
            daemon=True
        )

    # ===== MarketPort =====

    def get_latest_candle(self, symbol=None, tf=None):
        if self.df is None or len(self.df) == 0:
            return None, None

        required_cols = [
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short",
            "range_high",
            "range_low"
        ]

        if not all(col in self.df.columns for col in required_cols):
            return None, None

        return len(self.df) - 1, self.df.iloc[-1]


    def subscribe_candle(self, callback):
        self.callbacks.append(callback)
        if not self.thread.is_alive():
            self.thread.start()

    # ===== internal =====

    def _start_ws(self):
        asyncio.run(self.client.connect())

    async def _on_ws_candle(self, candle: dict):

        row = {
            "time": pd.to_datetime(candle["time"], unit="s"),
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
            "volume": candle["volume"]
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
            "range_low"
        ]

        if not all(col in df.columns for col in required_cols):
            return

    # chỉ update df sống khi đã đủ feature
        self.df = df

        print("ADAPTER CHECK:", last_row[[
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short"
        ]])

        for cb in self.callbacks:
            cb(i, last_row, df)

