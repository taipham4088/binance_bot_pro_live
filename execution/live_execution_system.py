# execution/live_execution_system.py
import time
import asyncio
import uuid
from types import SimpleNamespace

from backend.core.execution_models import ExecutionPlan, PlanAction, PositionSide
from trading_core.execution_policy.position_projector import NetPositionProjector
from execution.state.execution_state import ExecutionState, ExecutionStatus
from execution.system.execution_lock import (
    ExecutionLock,
    ExecutionBusy,
    ExecutionPhase,
)
from execution.reconciliation.restart_guard import RestartGuard
from execution.reconciliation_supervisor import (
    ReconciliationSupervisor,
    PositionSnapshot,
    ReconciliationStatus,
)


class LiveExecutionSystem:
    """
    Production-grade Execution System
    - KhÃ´ng quyáº¿t Ä‘á»‹nh trade
    - KhÃ´ng Ä‘á»c intent
    - Chá»‰ thá»±c thi ExecutionPlan
    """

    def __init__(
        self,
        session_id: str,
        exchange_adapter,
        sync_engine,
        state_store=None,
        execution_state=None,
    ):
        self.exchange = exchange_adapter
        self.session_id = session_id
        self.sync_engine = sync_engine
        self.sync_engine.live_execution_system = self
        # ðŸ”¥ bind exchange back to sync engine
        self.sync_engine.exchange = self.exchange

        print("LIVE SYSTEM POSITION ENGINE:", id(self.sync_engine.position))
        # ðŸ”¥ BIND SYNC ENGINE (fix floating pnl realtime)
        try:
            if hasattr(self.exchange, "set_sync_engine"):
                self.exchange.set_sync_engine(self.sync_engine)
            elif hasattr(self.exchange, "set_event_handler"):
                self.exchange.set_event_handler(self.sync_engine.on_user_event)
            else:
                # fallback direct binding
                self.exchange.sync_engine = self.sync_engine
        except Exception as e:
            print("[LiveExecutionSystem] sync bind error:", e)

        self.state_store = state_store

        self.position_projector = NetPositionProjector()
        self.freeze_system = sync_engine.freezer if sync_engine else None

        self.execution_state = execution_state

        # ðŸ”¥ Táº O LOCK TRÆ¯á»šC
        self.execution_lock = ExecutionLock()

        # ðŸ”¥ GIá»œ restart_guard má»›i an toÃ n
        self.restart_guard = RestartGuard(self)

        self.running = False
        self._reconcile_interval = 3
        self._reconcile_task = None
        # execution_id -> bracket payload (symbol, side, qty, sl/tp)
        self._pending_brackets = {}
        self._last_intent_metadata = {}
        self._execution_to_intent = {}

    # =========================
    # LIFECYCLE
    # =========================

    async def start(self):
        if self.running:
            return

        self.running = True

        self.restart_guard.run()

        if self.execution_state and self.execution_state.is_frozen():
            print("[LiveExecutionSystem] system frozen on startup")
            return

        # ðŸ”¥ START USER STREAM (QUAN TRá»ŒNG NHáº¤T)
        try:
            await self.exchange.start_user_stream()
            print("[LiveExecutionSystem] user stream started")
        except Exception as e:
            print("[LiveExecutionSystem] user stream error:", e)

        await self.supervisor.start()

        print("[LiveExecutionSystem] started")

    # =========================
    # PLAN VALIDATION (Production Guard)
    # =========================

    def _validate_plan(self, plan: ExecutionPlan):

        if plan.action in (PlanAction.NOOP, PlanAction.BLOCK):
            return

        if not plan.symbol:
            raise ValueError(
                f"INVALID_PLAN: symbol is required for action {plan.action}"
            )

        if plan.quantity is None or float(plan.quantity) <= 0:
            raise ValueError(
                f"INVALID_PLAN: quantity must be > 0 for action {plan.action}"
            )

    # =========================
    # CORE EXECUTION
    # =========================

    def register_pending_brackets(
        self,
        *,
        execution_id: str,
        client_order_id: str | None = None,
        symbol: str,
        side: str,
        quantity: float,
        metadata: dict,
    ):
        if not execution_id or not isinstance(metadata, dict):
            return
        sl = metadata.get("sl")
        tp = metadata.get("tp")
        print(
            "[BRACKET REGISTER]",
            "symbol=", symbol,
            "side=", side,
            "qty=", quantity,
            "sl=", sl,
            "tp=", tp,
            "execution_id=", execution_id,
            "client_order_id=", client_order_id,
        )
        if not sl and not tp:
            return
        bracket_key = f"{symbol}-{execution_id}"
        self._pending_brackets[bracket_key] = {
            "symbol": symbol,
            "side": side,
            "quantity": float(quantity),
            "sl": sl,
            "tp": tp,
        }
        print("[BRACKET STORED]", bracket_key)

    def pop_pending_brackets(self, key: str):
        if not key:
            return None
        return self._pending_brackets.pop(key, None)

    async def execute_plan(self, plan: ExecutionPlan):

        # =========================
        # TRADE PERMISSION GUARD
        # =========================
        # ðŸ”¥ TEMP FIX: cho phÃ©p trade khi READY
        if self.execution_state.status not in ["READY"]:
            raise Exception(
                f"EXECUTION_NOT_READY: {self.execution_state.status}"
            )

        # =========================
        # PLAN VALIDATION
        # =========================
        self._validate_plan(plan)

        # =========================
        # NOOP / BLOCK
        # =========================
        if plan.action in (PlanAction.NOOP, PlanAction.BLOCK):
            return

        execution_id = getattr(plan, "execution_id", None)

        # 🔥 IMPORTANT — keep same execution id if already exists
        if execution_id is None:
            execution_id = f"manual_{uuid.uuid4().hex[:8]}"
            object.__setattr__(plan, "execution_id", execution_id)

        symbol = plan.symbol
        quantity = float(plan.quantity)
        metadata = getattr(plan, "metadata", {}) or {}
        print("[PLAN METADATA]", metadata)
        intent_id = (
            getattr(plan, "intent_id", None)
            or metadata.get("intent_id")
            or execution_id
        )
        self._last_intent_metadata[intent_id] = metadata
        self._execution_to_intent[execution_id] = intent_id

        # =========================
        # EXECUTION
        # =========================
        # 🔥 SIGNAL TIME
        signal_time = time.time()

        print("EXECUTION_ID (LIVE):", execution_id)

        try:
            # register signal first
            self.sync_engine.register_signal(
                symbol,
                execution_id,
                signal_time,
                None
            )

        except Exception as e:
            print("[LATENCY REGISTER ERROR]", e)


        # 🔥 ORDER SENT TIME
        order_sent_time = time.time()

        try:
            self.sync_engine.update_order_sent(
                symbol,
                execution_id,
                order_sent_time
            )

        except Exception as e:
            print("[ORDER SENT UPDATE ERROR]", e)


        # 🔥 ATTACH METADATA AFTER update_order_sent (FIX BUG)
        try:
            key = f"{symbol}-{execution_id}"
            latency = self.sync_engine._latency_buffer.setdefault(key, {})
            latency["metadata"] = metadata

            print("LIVE SYNC ENGINE ID:", id(self.sync_engine))
            print("LIVE LATENCY BUFFER ID:", id(self.sync_engine._latency_buffer))
            print("[ATTACH METADATA]", key, latency["metadata"])

        except Exception as e:
            print("[METADATA ATTACH ERROR]", e)

        # =========================
        # OPEN
        # =========================
        if plan.action == PlanAction.OPEN:

            # 🔥 REGISTER BEFORE OPEN (FIX RACE CONDITION)
            try:
                self.register_pending_brackets(
                    execution_id=execution_id,
                    client_order_id=execution_id,
                    symbol=symbol,
                    side=plan.side.value.upper(),
                    quantity=quantity,
                    metadata=getattr(plan, "metadata", {}) or {},
                )

                print(
                    "[BRACKET PRE-REGISTER]",
                    symbol,
                    execution_id,
                    getattr(plan, "metadata", {})
                )

            except Exception as e:
                print("[BRACKET REGISTER ERROR]", e)

            # Send order AFTER register
            fill = await self.exchange.open_position(
                symbol=symbol,
                side=plan.side.value.upper(),
                quantity=quantity,
                execution_id=execution_id
            )

            actual_qty = float(getattr(fill, "filled_quantity", 0))

            # 🔥 don't fail on zero fill (websocket confirm later)
            if actual_qty <= 0:
                print("[EXECUTION] OPEN waiting fill via websocket")

            else:
                self.timeline.apply_fill(
                    side=plan.side.value.lower(),
                    filled_qty=actual_qty,
                )

        # =========================
        # CLOSE / REDUCE
        # =========================
        elif plan.action in (PlanAction.CLOSE, PlanAction.REDUCE):

            fill = await self.exchange.close_position(
                symbol=symbol,
                quantity=quantity,
                execution_id=execution_id
            )

            actual_qty = float(getattr(fill, "filled_quantity", 0))

            # 🔥 don't fail on zero fill (websocket confirm later)
            if actual_qty <= 0:
                print("[EXECUTION] CLOSE waiting fill via websocket")

            else:
                self.timeline.apply_fill(
                    side=self.timeline._state.position.side,
                    filled_qty=actual_qty,
                )

        else:
            raise Exception(f"UNSUPPORTED_PLAN_ACTION: {plan.action}")

    def _resolve_position_side(self, side):
        if isinstance(side, PositionSide):
            return side

        normalized = str(side or "").strip().upper()
        if normalized == "LONG":
            return PositionSide.LONG
        if normalized == "SHORT":
            return PositionSide.SHORT
        return None

    # ===========================================================
    async def close_manual_position(self, symbol, size, side):

        try:
            from backend.core.execution_models import (
                ExecutionPlan,
                PlanAction,
                PositionSide
            )

            # 🔥 create dummy intent
            class ManualIntent:
                def __init__(self):
                    self.id = f"manual_auto_close"
                    self.symbol = symbol
                    self.target_side = "FLAT"

            intent = ManualIntent()

            # 🔥 acquire execution lock
            execution_id = self.execution_lock.acquire(intent)
            print("EXECUTION_ID (LIVE):", execution_id)
            # 🔥 wait until position stable (avoid partial close)
            last_size = None

            for _ in range(6):  # ~300ms max
                await asyncio.sleep(0.05)

                try:
                    latest_position = None
                    for p in self.sync_engine.position.get_all():
                        if p.symbol == symbol:
                            latest_position = p
                            break

                    if latest_position:
                        current_size = abs(float(latest_position.size))

                        if last_size is not None and abs(current_size - last_size) < 1e-12:
                            size = current_size
                            side = str(latest_position.side).upper()
                            break

                        last_size = current_size

                except Exception:
                    pass

            for p in self.sync_engine.position.get_all():
                if p.symbol == symbol:
                    size = abs(float(p.size))
                    side = str(p.side).upper()
                    break

            # 🔥 set phase
            self.execution_lock.update_phase(
                execution_id,
                ExecutionPhase.CLOSING
            )

            plan = ExecutionPlan(
                symbol=symbol,
                action=PlanAction.CLOSE,
                side=PositionSide[side],
                quantity=size,
                reduce_only=True,
                reason="manual_open_guard",
                source="manual_override",
                timestamp=time.time()
            )

            # 🔥 inject execution_id
            object.__setattr__(plan, "execution_id", execution_id)

            # 🔥 execute
            await self.execute_plan(plan)

            # 🔥 release
            self.execution_lock.release(execution_id)

        except Exception as e:

            print("[Manual Auto Close Error]", e)

            # 🔥 abort correctly
            self.execution_lock.abort(
                reason="manual_auto_close_failed",
                by="manual_guard"
            )

    # =========================
    async def stop(self):

        self.running = False

        try:
            if hasattr(self, "supervisor"):
                await self.supervisor.stop()
        except Exception:
            pass

        try:
            await self.exchange.stop_user_stream()
        except Exception:
            pass

        print("[LiveExecutionSystem] stopped")

    # =========================
    # SAFE RESTART
    # =========================

    async def restart(self):

        print("[LiveExecutionSystem] restart begin")

        try:
            # stop execution system
            await self.stop()
        except Exception as e:
            print("[LiveExecutionSystem] stop error during restart:", e)

        await asyncio.sleep(1)

        try:
            # clear freeze náº¿u cÃ³
            if self.execution_state and self.execution_state.is_frozen():
                print("[LiveExecutionSystem] clearing frozen state")
                self.execution_state.to_syncing()

            # restart system
            await self.start()

        except Exception as e:
            print("[LiveExecutionSystem] restart failed:", e)
            raise

        print("[LiveExecutionSystem] restart complete")

    def health_check(self):

        try:
            state = self.execution_state.status
        except Exception:
            state = "UNKNOWN"

        return {
            "status": str(state),
            "running": self.running
        }
