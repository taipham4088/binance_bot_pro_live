import inspect
import pandas as pd
from pathlib import Path

from trading_core.data.feature_builder import build_features
from trading_core.data.range_trend_profiles import merge_tolerance_for_regime_interval
from trading_core.data.resampler import resample_ohlc_from_entry

# Rolling cap on native regime bars (REST bootstrap + merged incremental resamples).
_REGIME_ROLLING_MAX = 500
# Throttle [DATA PIPELINE] prints (entry 1m → avoid log spam).
_DATA_PIPELINE_LOG_EVERY = 50


def _log_engine_create_source(session_id: str) -> None:
    """Temporary: show who constructed LiveFeatureEngine (import side-effect vs LiveService)."""
    st = inspect.stack()
    # stack[0]=here, [1]=__init__, [2]=direct caller of LiveFeatureEngine(...)
    fr = st[2] if len(st) > 2 else st[-1]
    print(
        "[ENGINE CREATE SOURCE]",
        f"file={fr.filename}",
        f"caller={fr.function}:{fr.lineno}",
        f"session={session_id!r}",
    )


def _entry_max_bars(entry_interval: str) -> int:
    k = (entry_interval or "5m").strip().lower()
    if k in ("1m", "5m", "15m"):
        return 3000
    if k == "1h":
        return 1000
    return 2000


class LiveFeatureEngine:
    """
    Synchronous feature pipeline: no background threads or timers.
    ``push_candle`` runs only when the market adapter calls it (e.g. Binance WS).
    """

    def __init__(
        self,
        min_bars: int = 300,
        session_id: str | None = None,
        *,
        entry_interval: str = "5m",
        regime_interval: str = "1h",
    ):
        self.entry_interval = (entry_interval or "5m").strip().lower()
        self.regime_interval = (regime_interval or "1h").strip().lower()
        self.df_entry = pd.DataFrame()
        self.df_regime = pd.DataFrame()
        self.min_bars = min_bars
        self.last_price = None
        self.session_id = (session_id or "live").strip().lower()
        self.bar_count = 0
        self.export_every_n = 5
        self._entry_cap = _entry_max_bars(self.entry_interval)
        print(
            "[FEATURE ENGINE CREATE]",
            f"id={id(self)}",
            f"session_id={self.session_id!r}",
            f"entry={self.entry_interval!r}",
            f"regime={self.regime_interval!r}",
        )
        _log_engine_create_source(self.session_id)

    @property
    def df_5m(self) -> pd.DataFrame:
        """Backward-compatible name: primary entry-timeframe bar frame."""
        return self.df_entry

    @staticmethod
    def _ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
        cols = ["time", "open", "high", "low", "close", "volume"]
        for c in cols:
            if c not in df.columns:
                raise ValueError(f"LiveFeatureEngine: missing column {c!r} for resample")
        out = df[cols].copy()
        out["time"] = pd.to_datetime(out["time"])
        for c in ("open", "high", "low", "close", "volume"):
            out[c] = pd.to_numeric(out[c], errors="coerce")
        return out.dropna(subset=["open", "high", "low", "close"])

    def _merge_regime_incremental(self, regime_new: pd.DataFrame) -> None:
        """
        Keep regime history across entry tail drops: merge resample of current entry
        window with existing native regime rows; cap length with tail(regime_max).
        """
        if regime_new is None or regime_new.empty:
            if self.df_regime is not None and len(self.df_regime) > _REGIME_ROLLING_MAX:
                self.df_regime = (
                    self.df_regime.sort_values("time")
                    .tail(_REGIME_ROLLING_MAX)
                    .reset_index(drop=True)
                )
            return

        regime_new = regime_new.copy()
        regime_new["time"] = pd.to_datetime(regime_new["time"])

        if self.df_regime is None or self.df_regime.empty:
            self.df_regime = regime_new
        else:
            base = self.df_regime.copy()
            base["time"] = pd.to_datetime(base["time"])
            combined = pd.concat([base, regime_new], ignore_index=True)
            combined = combined.sort_values("time").drop_duplicates(
                subset=["time"], keep="last"
            )
            self.df_regime = combined

        if len(self.df_regime) > _REGIME_ROLLING_MAX:
            self.df_regime = (
                self.df_regime.sort_values("time")
                .tail(_REGIME_ROLLING_MAX)
                .reset_index(drop=True)
            )

    # =========================
    # BOOTSTRAP
    # =========================
    def bootstrap(self, df_entry: pd.DataFrame, df_regime: pd.DataFrame):

        self.df_entry = df_entry.copy()
        self.df_regime = df_regime.copy()

        self.df_entry = build_features(
            self.df_entry,
            self.df_regime,
            regime_interval=self.regime_interval,
        )

    # =========================
    # PUSH NEW CANDLE
    # =========================
    def push_candle(self, candle: dict):
        self.last_price = candle["close"]

        new_row = pd.DataFrame([candle])

        if (
            not self.df_entry.empty
            and self.df_entry.iloc[-1]["time"] == new_row.iloc[0]["time"]
        ):
            self.df_entry.loc[
                self.df_entry.index[-1],
                ["open", "high", "low", "close", "volume"],
            ] = [
                new_row.iloc[0]["open"],
                new_row.iloc[0]["high"],
                new_row.iloc[0]["low"],
                new_row.iloc[0]["close"],
                new_row.iloc[0]["volume"],
            ]
        else:
            self.df_entry = pd.concat([self.df_entry, new_row], ignore_index=True)

        self.df_entry = self.df_entry.tail(self._entry_cap).reset_index(drop=True)

        if len(self.df_entry) < self.min_bars:
            return None

        self.df_entry = self.df_entry.sort_values("time").reset_index(drop=True)

        try:
            ohlc = self._ohlcv_frame(self.df_entry)
        except ValueError:
            return None

        if ohlc.empty:
            return None

        regime_new = resample_ohlc_from_entry(
            ohlc, self.regime_interval, drop_last_incomplete=True
        )
        self._merge_regime_incremental(regime_new)

        self.df_regime = self.df_regime.sort_values("time").reset_index(drop=True)

        df_feat = build_features(
            self.df_entry.copy(),
            self.df_regime.copy(),
            regime_interval=self.regime_interval,
        )

        cols = ["time", "ema200", "close_1h", "valid_long", "valid_short"]
        cols = [c for c in cols if c in df_feat.columns]

        df_feat = df_feat.ffill()
        df_feat = df_feat.reset_index(drop=True)

        feature_cols = [
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short",
            "range_high",
            "range_low",
        ]

        for c in feature_cols:
            if c not in self.df_entry.columns:
                self.df_entry[c] = None

        self.df_entry.loc[:, feature_cols] = df_feat.loc[:, feature_cols]

        print("FEATURE CHECK:")
        print(
            self.df_entry.tail(1)[
                [
                    "time",
                    "ema200",
                    "close_1h",
                    "valid_long",
                    "valid_short",
                    "range_high",
                    "range_low",
                ]
            ]
        )

        i = len(self.df_entry) - 1
        self.bar_count += 1
        if self.bar_count % _DATA_PIPELINE_LOG_EVERY == 0:
            print(
                "[DATA PIPELINE]\n"
                f"entry_interval = {self.entry_interval}\n"
                f"entry_bars = {len(self.df_entry)}\n"
                f"regime_bars = {len(self.df_regime)}"
            )
        if self.bar_count % self.export_every_n == 0:
            self._export_debug_csv()
        return i, self.df_entry.iloc[-1], self.df_entry

    def export_now(self) -> int | None:
        """Immediate debug export (latest up to 200 bars). Read-only; no trading impact."""
        sid = (
            "live"
            if self.session_id == "live"
            else "shadow"
            if self.session_id == "shadow"
            else self.session_id
        )
        try:
            n = self._export_debug_csv(log_line=False)
            if n is not None:
                print(f"[CANDLE EXPORT] manual export {sid} {n} bars")
            else:
                print(f"[CANDLE EXPORT] manual export {sid} failed or empty")
            return n
        except Exception as e:
            print("[CANDLE EXPORT ERROR]", e)
            return None

    def _export_debug_csv(self, *, log_line: bool = True) -> int | None:
        try:
            sid = (
                "live"
                if self.session_id == "live"
                else "shadow"
                if self.session_id == "shadow"
                else self.session_id
            )
            out_dir = Path("data") / "debug"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"candle_{sid}.csv"

            df = self.df_entry.copy()
            if df.empty:
                return None

            df = df.sort_values("time").tail(200).reset_index(drop=True)

            base_cols = [
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "ema200",
                "close_1h",
                "valid_long",
                "valid_short",
                "range_high",
                "range_low",
                "break_up_id",
                "break_down_id",
                "bars_since_break_up",
                "bars_since_break_down",
            ]
            keep = [c for c in base_cols if c in df.columns]

            required = [
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "ema200",
                "close_1h",
                "valid_long",
                "valid_short",
                "range_high",
                "range_low",
            ]
            for col in required:
                if col not in keep:
                    df[col] = None
                    keep.append(col)

            ordered = required + [c for c in keep if c not in required]
            df[ordered].to_csv(out_path, index=False)
            n = len(df)
            if log_line:
                print(f"[CANDLE EXPORT] {sid} exported {n} bars")
            return n
        except Exception:
            return None

    # =========================
    # MERGE REGIME FEATURES (debug / offline)
    # =========================
    def _merge_regime(self, df_entry: pd.DataFrame, df_regime: pd.DataFrame):
        drop_cols = [
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short",
            "range_high",
            "range_low",
        ]

        for c in drop_cols:
            if c in df_entry.columns:
                df_entry = df_entry.drop(columns=c)

        df_feat = build_features(
            df_entry.copy(),
            df_regime.copy(),
            regime_interval=self.regime_interval,
        )

        h1_cols = [
            "time",
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short",
            "range_high",
            "range_low",
        ]

        df_h1_feat = df_feat[h1_cols].drop_duplicates("time")

        df_entry = df_entry.sort_values("time")
        df_h1_feat = df_h1_feat.sort_values("time")

        tol = merge_tolerance_for_regime_interval(self.regime_interval)
        df_merge = pd.merge_asof(
            df_entry,
            df_h1_feat,
            on="time",
            direction="backward",
            tolerance=tol,
        )

        return df_merge
