import pandas as pd
from trading_core.data.feature_builder import build_features
from pathlib import Path

class LiveFeatureEngine:

    def __init__(self, min_bars: int = 300, session_id: str | None = None):
        self.df_5m = pd.DataFrame()
        self.df_1h = pd.DataFrame()
        self.min_bars = min_bars
        self.last_price = None
        self.session_id = (session_id or "live").strip().lower()
        self.bar_count = 0
        self.export_every_n = 5

    # =========================
    # BOOTSTRAP
    # =========================
    def bootstrap(self, df_5m: pd.DataFrame, df_1h: pd.DataFrame):

        self.df_5m = df_5m.copy()
        self.df_1h = df_1h.copy()

        # build feature ngay từ bootstrap
        self.df_5m = build_features(self.df_5m, self.df_1h)

    # =========================
    # PUSH NEW CANDLE
    # =========================
    def push_candle(self, candle: dict):
        # ⭐ cập nhật giá market mới nhất
        self.last_price = candle["close"]

        # append candle mới
        new_row = pd.DataFrame([candle])

        # nếu candle time trùng với candle cuối → update thay vì append
        if not self.df_5m.empty and self.df_5m.iloc[-1]["time"] == new_row.iloc[0]["time"]:

            # chỉ update OHLCV
            self.df_5m.loc[self.df_5m.index[-1], ["open","high","low","close","volume"]] = [
                new_row.iloc[0]["open"],
                new_row.iloc[0]["high"],
                new_row.iloc[0]["low"],
                new_row.iloc[0]["close"],
                new_row.iloc[0]["volume"]
            ]

        else:
            self.df_5m = pd.concat(
                [self.df_5m, new_row], 
                ignore_index=True
            )

        # giữ window 2000 bars
        self.df_5m = self.df_5m.tail(1200).reset_index(drop=True)

        if len(self.df_5m) < self.min_bars:
            return None
        
        if len(self.df_5m) % 12 == 0:
            self.df_1h = self._build_1h(self.df_5m)

        # build feature lại cho toàn bộ window
        # đảm bảo time sorted (QUAN TRỌNG)
        self.df_5m = self.df_5m.sort_values("time").reset_index(drop=True)
        self.df_1h = self.df_1h.sort_values("time").reset_index(drop=True)

        df_feat = build_features(self.df_5m.copy(), self.df_1h.copy())
        
        cols = ["time","ema200","close_1h","valid_long","valid_short"]
        cols = [c for c in cols if c in df_feat.columns]

        df_feat = df_feat.ffill()
        df_feat = df_feat.reset_index(drop=True)

        feature_cols = [
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short",
            "range_high",
            "range_low"
        ]

        # đảm bảo column tồn tại
        for c in feature_cols:
            if c not in self.df_5m.columns:
                self.df_5m[c] = None

        # copy feature vào dataframe sống (safe alignment)
        self.df_5m.loc[:, feature_cols] = df_feat.loc[:, feature_cols]
        
        print("FEATURE CHECK:")
        print(self.df_5m.tail(1)[[
            "time",
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short",
            "range_high",
            "range_low"
        ]])

        i = len(self.df_5m) - 1
        self.bar_count += 1
        if self.bar_count % self.export_every_n == 0:
            self._export_debug_csv()
        return i, self.df_5m.iloc[-1], self.df_5m

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
            sid = "live" if self.session_id == "live" else "shadow" if self.session_id == "shadow" else self.session_id
            out_dir = Path("data") / "debug"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"candle_{sid}.csv"

            df = self.df_5m.copy()
            if df.empty:
                return None

            # Keep debug export compact and predictable.
            df = df.sort_values("time").tail(200).reset_index(drop=True)

            base_cols = [
                "time", "open", "high", "low", "close", "volume",
                "ema200", "close_1h", "valid_long", "valid_short",
                "range_high", "range_low",
                "break_up_id", "break_down_id",
                "bars_since_break_up", "bars_since_break_down",
            ]
            keep = [c for c in base_cols if c in df.columns]

            # Ensure required columns always exist in output.
            required = [
                "time", "open", "high", "low", "close", "volume",
                "ema200", "close_1h", "valid_long", "valid_short",
                "range_high", "range_low",
            ]
            for col in required:
                if col not in keep:
                    df[col] = None
                    keep.append(col)

            # Stable column order: required first, then optional extras present.
            ordered = required + [c for c in keep if c not in required]
            df[ordered].to_csv(out_path, index=False)
            n = len(df)
            if log_line:
                print(f"[CANDLE EXPORT] {sid} exported {n} bars")
            return n
        except Exception:
            return None

    # =========================
    # BUILD H1 CONTEXT
    # =========================
    def _build_1h(self, df_5m: pd.DataFrame):

        df = df_5m.copy()

        # đảm bảo datetime
        df["time"] = pd.to_datetime(df["time"])

        # sort time
        df = df.sort_values("time")

        # ⚠️ guard: bỏ candle cuối (candle chưa đóng)
        if len(df) > 1:
            df = df.iloc[:-1]

        # set index cho resample
        df = df.set_index("time")

        # build H1
        df_1h = df.resample("1h").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        })

        df_1h = df_1h.dropna()

        df_1h = df_1h.reset_index()

        return df_1h

    # =========================
    # MERGE H1 FEATURES INTO 5M (FINAL LIVE SAFE)
    # =========================
    def _merge_h1(self, df_5m: pd.DataFrame, df_1h: pd.DataFrame):
        # ===== REMOVE OLD H1 COLUMNS (CỰC KỲ QUAN TRỌNG) =====
        drop_cols = [
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short",
            "range_high",
            "range_low"
        ]

        for c in drop_cols:
            if c in df_5m.columns:
                df_5m = df_5m.drop(columns=c)

        # ===== BUILD FULL FEATURE FROM CORE PIPELINE =====
        df_feat = build_features(df_5m.copy(), df_1h.copy())

        h1_cols = [
            "time",
            "ema200",
            "close_1h",
            "valid_long",
            "valid_short",
            "range_high",
            "range_low"
        ]

        df_h1_feat = df_feat[h1_cols].drop_duplicates("time")

        df_5m = df_5m.sort_values("time")
        df_h1_feat = df_h1_feat.sort_values("time")

        df_merge = pd.merge_asof(
            df_5m,
            df_h1_feat,
            on="time",
            direction="backward"
        )

        return df_merge
        
# instance global cho các module khác import      
live_feature_engine = LiveFeatureEngine()
