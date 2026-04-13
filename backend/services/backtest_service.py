import os

import pandas as pd

BACKTEST_OUTPUT_DIR = os.path.join("data", "backtest", "output")
BACKTEST_LATEST_CSV = os.path.join(BACKTEST_OUTPUT_DIR, "backtest_latest.csv")

from trading_core.runners.backtest import prepare_data
from trading_core.data.range_trend_profiles import normalize_range_trend_engine_key
from trading_core.runtime.context import RuntimeContext
from trading_core.engines.dual_engine import DualEngine

from backend.adapters.account.paper_account_adapter import PaperAccountAdapter


def _initial_balance_from_config(config, default: float = 10000.0) -> float:
    if isinstance(config, dict):
        raw = config.get("initial_balance", default)
    else:
        raw = getattr(config, "initial_balance", default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


class BacktestService:
    """CSV backtest using trading_core DualEngine (no StrategyHost ports required)."""
    def __init__(self):
        self._stop_requested = False

    @staticmethod
    def _remove_latest_csv() -> None:
        if os.path.isfile(BACKTEST_LATEST_CSV):
            try:
                os.remove(BACKTEST_LATEST_CSV)
            except OSError:
                pass

    @staticmethod
    def _write_latest_csv(trades) -> None:
        os.makedirs(BACKTEST_OUTPUT_DIR, exist_ok=True)
        df = pd.DataFrame(trades)
        df.to_csv(BACKTEST_LATEST_CSV, index=False)

    def run(self, session, csv_path):
        self._stop_requested = False
        print(f"[BACKTEST RUN] session_id={session.id}")
        print(f"[BACKTEST RUN] csv_path={csv_path}")
        os.makedirs(BACKTEST_OUTPUT_DIR, exist_ok=True)
        self._remove_latest_csv()
        eng = getattr(session.config, "engine", None)
        if isinstance(session.config, dict):
            eng = session.config.get("engine", eng)
        df = prepare_data(csv_path, engine_key=normalize_range_trend_engine_key(eng))
        print(f"[BACKTEST RUN] rows={len(df)}")
        context = RuntimeContext(session.config)
        initial_balance = _initial_balance_from_config(session.config)
        account = PaperAccountAdapter(initial_balance)
        engine = DualEngine(session.config, context, account=account)
        session.account = account
        session.engine = engine

        session.state_bus.on_equity(0, account.get_equity())

        total = len(df)
        for i in range(80, total):
            if self._stop_requested:
                print(f"[BACKTEST] stop requested session_id={session.id}")
                session.status = "STOPPED"
                break
            engine.on_bar(i, df.iloc[i], df)

            upd = {"trade_count": len(engine.trades)}
            if i == 80 or i % 2000 == 0:
                upd["backtest_progress"] = i / total
            session.state_bus.on_status(upd)

            if engine.equity_tracker.curve:
                t, eq = engine.equity_tracker.curve[-1]
                session.state_bus.on_equity(t, eq)

        for trade in engine.trades:
            session.state_bus.on_trade(trade)

        if session.status != "STOPPED":
            session.state_bus.on_status(
                {
                    "backtest_progress": 1.0,
                    "trade_count": len(engine.trades),
                }
            )
            session.state_bus.on_equity(total, account.get_equity())
            session.status = "FINISHED"
        self._write_latest_csv(engine.trades)
        return engine.trades, session.state_bus.snapshot()

    def stop(self):
        self._stop_requested = True

    def export(self, session):
        if not getattr(session, "engine", None):
            raise RuntimeError("Backtest engine not available")

        self._write_latest_csv(session.engine.trades)
        return os.path.abspath(BACKTEST_LATEST_CSV)
