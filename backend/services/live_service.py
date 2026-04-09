import logging
logger = logging.getLogger("LIVE")
from execution.live_bootstrap import build_live_execution_system
from backend.adapters.market.binance_market_adapter import BinanceMarketAdapter
from backend.adapters.account.dummy_account_adapter import DummyAccountAdapter
from execution.mode_router import ModeRouter
from backend.runtime.live_runner import LiveRunner
from backend.core.strategy_host import StrategyHost
from backend.live.health_loop import HealthLoop

class LiveService:

    def __init__(self):
        self.host = StrategyHost()

    def start(self, session, symbol: str, timeframe: str):
        # Idempotency guard: avoid duplicate runner/market wiring per session.
        if getattr(session, "runner", None) and session.runner.is_alive():
            return session.id

        # Reuse execution stack created by TradingSession.start(); never build a second one.
        live_system = getattr(session, "live_system", None)
        if live_system is None:
            live_system = build_live_execution_system(
                config=session.config,
                event_bus=session.state_bus,
                logger=logger,
                persistence_key=session.id,
            )
            session.live_system = live_system
        # ===== HEALTH LOOP =====
        health_loop = HealthLoop(
            state_engine=session.system_state,   # ✅ đúng engine
            sync_engine=live_system.sync_engine,
            execution_state=live_system.execution_state, 
        )

        session.health_loop = health_loop
        import asyncio
        loop = asyncio.get_event_loop()
        session.health_task = loop.create_task(health_loop.start())

        orchestrator = live_system.orchestrator
        session.live_system = live_system
        # TradingSession.start already starts the execution system.
        # If this path is invoked before that, start once safely.
        if not getattr(live_system, "running", False):
            loop.create_task(live_system.start())

        # ===== live ports =====
        market = BinanceMarketAdapter(symbol, timeframe, session_id=session.id)
        mode_router = ModeRouter(
            mode=session.config.mode,
            live_system=live_system,
            orchestrator=orchestrator
        )

        execution = mode_router.build_execution_port()
        account = DummyAccountAdapter(session.config.initial_balance)

        session.market = market
        session.execution = execution
        session.account = account

        # BinanceMarketAdapter has no async start(); feed starts when runner subscribes.

        # small delay to ensure websocket connected
        import time
        time.sleep(1)

        # ===== core =====
        engine = self.host.create_engine(
            config=session.config,
            market=market,
            execution=execution,
            account=account
        )


        session.build(
            engine=engine,  # dùng engine vừa tạo
            executor=execution,
            data_feed=market,
            risk_system=None
        )

        # ===== runner =====
        runner = LiveRunner(session, market)
        session.runner = runner
        runner.start()

        return session.id

    def stop(self, session):

        session.status = "STOPPING"

        # stop runner
        if hasattr(session, "runner") and session.runner:
            session.runner.stop()

            if session.runner.is_alive():
                session.runner.join(timeout=5)


        # stop market
        if hasattr(session, "market") and session.market:
            session.market.stop()

        # stop health loop
        if hasattr(session, "health_loop") and session.health_loop:
            session.health_loop.stop()

        if hasattr(session, "health_task") and session.health_task:
            session.health_task.cancel()


        # stop live execution system
        if hasattr(session, "live_system") and session.live_system:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(session.live_system.stop())
            except RuntimeError:
                pass
