import os
from datetime import datetime

import pandas as pd

from trading_core.runners.backtest import prepare_data
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

    def run(self, session, csv_path):
        print(f"[BACKTEST RUN] session_id={session.id}")
        print(f"[BACKTEST RUN] csv_path={csv_path}")
        df = prepare_data(csv_path)
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

        session.state_bus.on_status(
            {
                "backtest_progress": 1.0,
                "trade_count": len(engine.trades),
            }
        )
        session.state_bus.on_equity(total, account.get_equity())

        session.status = "FINISHED"
        return engine.trades, session.state_bus.snapshot()

    def export(self, session):
        if not getattr(session, "engine", None):
            raise RuntimeError("Backtest engine not available")

        trades = session.engine.trades
        df = pd.DataFrame(trades)

        os.makedirs("data/backtest/output", exist_ok=True)
        filename = f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = os.path.join("data", "backtest", "output", filename)
        df.to_csv(path, index=False)
        return os.path.abspath(path)
