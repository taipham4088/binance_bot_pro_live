from trading_core.runners.backtest import prepare_data

from backend.adapters.market.paper_market_adapter import PaperMarketAdapter
from backend.adapters.execution.paper_execution_adapter import PaperExecutionAdapter
from backend.adapters.account.paper_account_adapter import PaperAccountAdapter

from backend.runtime.live_runner import LiveRunner
from backend.core.strategy_host import StrategyHost


class PaperService:

    def __init__(self):
        self.host = StrategyHost()

    def start(self, session, csv_path, speed=0.2):

        df = prepare_data(csv_path)

        # ===== init ports =====
        market = PaperMarketAdapter(df, speed=speed)
        execution = PaperExecutionAdapter()
        if isinstance(session.config, dict):
            raw_ib = session.config.get("initial_balance", 10000)
        else:
            raw_ib = getattr(session.config, "initial_balance", 10000)
        try:
            ib = float(raw_ib)
        except (TypeError, ValueError):
            ib = 10000.0
        account = PaperAccountAdapter(ib)

        session.market = market
        session.execution = execution
        session.account = account

        # ===== create core engine via ports =====
        engine = self.host.create_engine(
            config=session.config,
            market=market,
            execution=execution,
            account=account
        )

        session.engine = engine

        # ===== runner vẫn giữ feed loop (tạm) =====
        runner = LiveRunner(session, market)
        session.runner = runner

        runner.start()
        return session.id

    def stop(self, session):
        if session.runner:
            session.runner.stop()
            session.status = "STOPPING"
