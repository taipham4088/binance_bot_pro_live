import time
from typing import Dict, Optional, List
from dataclasses import dataclass

# Core modules (đã hoàn thành ở STEP 11)
from backend.core.execution.execution_engine import ExecutionEngine, OrderIntent
from backend.core.execution.execution_slot_manager import (
    ExecutionSlotManager,
    ExecutionSlotKey,
)
from backend.core.risk.risk_engine import RiskEngine
from backend.core.strategy.strategy_orchestrator import (
    StrategyOrchestrator,
    TradeIntent,
)
from backend.core.warning.reversal_warning import ReversalWarningEngine


# =========================
# Session Model
# =========================

@dataclass
class SessionConfig:
    exchange: str
    environment: str          # live | paper
    mode: str                 # live | paper | backtest
    initial_equity: float
    max_position_size: float


@dataclass
class SessionState:
    session_id: str
    status: str               # CREATED | RUNNING | STOPPED
    active_symbol: Optional[str] = None


# =========================
# Session Lifecycle Manager
# =========================

class SessionLifecycleManager:
    """
    STEP 11 / Module 6

    Responsibilities:
    - Own session lifecycle
    - Glue ExecutionEngine, RiskEngine, StrategyOrchestrator, WarningEngine
    - Enforce lifecycle order (STOP → RESET → APPLY → START)
    - NO direct execution authority from Control Plane
    """

    def __init__(
        self,
        session_id: str,
        config: SessionConfig,
        slot_manager: ExecutionSlotManager,
    ):
        self.session_id = session_id
        self.config = config
        self.state = SessionState(
            session_id=session_id,
            status="CREATED",
        )

        # --- Core Engines ---
        self.risk_engine = RiskEngine(
            initial_equity=config.initial_equity
        )

        self.execution_engine = ExecutionEngine(
            session_id=session_id,
            mode=config.mode,
            slot_key=ExecutionSlotKey(
                exchange=config.exchange,
                environment=config.environment,
                api_key="__SESSION_KEY__",  # resolved externally
            ),
            slot_manager=slot_manager,
            risk_engine=self.risk_engine,
        )

        self.strategy_orchestrator = StrategyOrchestrator(
            max_position_size=config.max_position_size
        )

        self.reversal_warning = ReversalWarningEngine()

    # -------------------------
    # Lifecycle Control
    # -------------------------

    def start(self) -> bool:
        """
        STARTING_BOT phase.
        """
        if self.state.status == "RUNNING":
            return True

        # 🔥 GLUE IMPORT (để trong hàm)
        from backend.core.state_hub import StateHub
        from backend.control_plane.engine_registry.engine_registry import engine_registry

        session_id = self.state.session_id

        # 1️⃣ Register session vào StateHub
        StateHub.get_instance().register_session(session_id)

        # 2️⃣ Start execution engine
        started = self.execution_engine.start()
        if not started:
            return False

        # 3️⃣ Attach execution graph (QUAN TRỌNG)
        engine_registry.attach_to_session(self)

        # 4️⃣ Mark session running
        self.state.status = "RUNNING"
        return True

    def stop(self) -> None:
        """
        STOPPING_BOT phase.
        """
        if self.state.status != "RUNNING":
            return

        self.execution_engine.stop()
        self.state.status = "STOPPED"

    # -------------------------
    # Config Switch Hooks
    # -------------------------

    def switch_active_symbol(self, symbol: str) -> bool:
        """
        STEP 9 – LIVE MODE SINGLE ACTIVE SYMBOL GUARD
        """
        if self.config.mode == "live":
            if self.state.active_symbol is not None:
                return False

        self.state.active_symbol = symbol
        return True

    def clear_active_symbol(self) -> None:
        self.state.active_symbol = None

    # -------------------------
    # Strategy → Execution Flow
    # -------------------------

    def on_strategy_intents(self, intents: List[TradeIntent]) -> None:
        """
        Entry point from Strategy Plane.
        """
        if self.state.status != "RUNNING":
            return

        resolved = self.strategy_orchestrator.resolve(intents)

        for r in resolved:
            # Enforce active symbol guard
            if (
                self.state.active_symbol is not None
                and r.symbol != self.state.active_symbol
            ):
                continue

            order_intent = OrderIntent(
                symbol=r.symbol,
                side=r.side,
                qty=r.qty,
                intent_id=f"{self.session_id}:{time.time()}",
            )
            self.execution_engine.handle_order_intent(order_intent)

    # -------------------------
    # Observer Snapshot
    # -------------------------

    def snapshot(self) -> dict:
        return {
            "session": {
                "id": self.session_id,
                "status": self.state.status,
                "active_symbol": self.state.active_symbol,
                "mode": self.config.mode,
            },
            "execution": self.execution_engine.snapshot(),
            "risk": self.risk_engine.snapshot(),
            "reversal_warning": self.reversal_warning.snapshot(),
        }

    def build_engine(self):
        engine_type = self.config.get("engine")
        if not engine_type:
            raise RuntimeError("Engine type not set in session config")

        engine = self.engine_registry.create(
            engine_type,
            config=self.config,
            context=self.context,
            market=self.market,
            execution=self.execution,
            account=self.account,
        )

        self.session.engine = engine
        print(f"[SESSION_LIFECYCLE] engine built for {self.session.id}")
