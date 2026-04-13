import pandas as pd
import time
import threading
from typing import Optional

from backend.live.market.live_feature_engine import LiveFeatureEngine


class BacktestReplayEngine:

    def __init__(self):
        self.df = None
        self.running = False
        self.index = 0
        self.thread = None
        self._replay_feature_engine: Optional[LiveFeatureEngine] = None

    # =========================
    # LOAD CSV
    # =========================

    def load_csv(self, file_name):

        path = f"data/backtest/input/{file_name}"

        df = pd.read_csv(path)

        df.columns = [c.lower() for c in df.columns]

        df["time"] = pd.to_datetime(df["timestamp"])

        df = df.sort_values("time").reset_index(drop=True)

        self.df = df
        self.index = 0

        print(f"[BACKTEST] Loaded CSV: {file_name}")
        print(f"[BACKTEST] Rows: {len(df)}")

    # =========================
    # START REPLAY
    # =========================

    def start(self):

        if self.df is None:
            print("[BACKTEST] No data loaded")
            return

        if self.running:
            print("[BACKTEST] Already running")
            return

        self._replay_feature_engine = LiveFeatureEngine(
            min_bars=300,
            session_id="replay",
            entry_interval="5m",
            regime_interval="1h",
        )

        self.running = True

        self.thread = threading.Thread(
            target=self._run,
            daemon=True
        )

        self.thread.start()

    # =========================
    # REPLAY LOOP
    # =========================

    def _run(self):

        print("[BACKTEST] Replay started")

        while self.running and self.index < len(self.df):

            row = self.df.iloc[self.index]

            candle = {
                "time": row["time"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"]
            }

            if self._replay_feature_engine is not None:
                self._replay_feature_engine.push_candle(candle)

            self.index += 1

            time.sleep(0.01)

        self.running = False

        print("[BACKTEST] Replay finished")

    # =========================
    # STOP
    # =========================

    def stop(self):

        self.running = False

        print("[BACKTEST] Replay stopped")


backtest_engine = BacktestReplayEngine()