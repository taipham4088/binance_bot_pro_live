from backend.execution.stub_execution import ExecutionEvent
from trading_core.execution_policy.policy_engine import ExecutionPolicyEngine
from trading_core.execution_policy.planner_guard import PlannerPolicyGuard
from execution.system.execution_lock import ExecutionPhase
import asyncio
from execution.orchestrator.planner import ExecutionPlanner
from execution.state.execution_state import ExecutionStatus
from execution.orchestrator.models import StepAction, TargetSide
import time
import uuid
from backend.observability.execution_metrics import (
    record_execution_start,
    record_execution_completed,
    record_execution_failure,
    record_reverse_cycle,
)


class ExecutionOrchestrator:

    def __init__(self,
                 execution_system,
                 execution_state,
                 execution_lock,
                 execution_window,
                 journal):

        self.execution_system = execution_system
        self.exchange = execution_system.exchange
        self.execution_state = execution_state
        self.execution_lock = execution_lock
        self.execution_window = execution_window
        self.journal = journal
        self.session_id = getattr(execution_system, "session_id", "default")

        self.planner = ExecutionPlanner()
              
        
        # 🔒 STEP 6
        self.policy = ExecutionPolicyEngine()
        self.planner_guard = PlannerPolicyGuard()
        # ===== Circuit Breaker =====
        self._consecutive_failures = 0
        self._failure_threshold = 3

    # ============================================================
    # ENTRY
    # ============================================================

    async def submit_intent(self, intent):
        print("[TRACE 2] ORCH INTENT", getattr(intent, "metadata", None))

        if self.execution_state.status != ExecutionStatus.READY:
            raise Exception("EXECUTION NOT READY")

        # =========================
        # 🔒 STEP 6 — POLICY GATE
        # =========================
        # 🔥 FORCE REFRESH BEFORE POLICY
        self.execution_system.exchange.trade.get_positions()
        await asyncio.sleep(0.2)
        
        positions = self.execution_system.sync_engine.position.get_all()
        current_net = self.execution_system.position_projector.project(positions)
        # (bạn cần 1 hàm project positions → NetPosition)

        decision = self.policy.evaluate_intent(intent, current_net)

        if decision.decision == "REFUSE":
            print("[POLICY] REFUSE:", decision.reason)
            return self._build_refuse(intent, decision.reason)

        if decision.decision == "FREEZE":
            print("[POLICY] FREEZE:", decision.reason)
            self.execution_state.freeze(decision.reason)
            return self._build_refuse(intent, decision.reason)

        # =========================
        # CHỈ TỪ ĐÂY TRỞ XUỐNG MỚI LÀ EXECUTION
        # =========================

        exec_id = self.execution_lock.acquire(intent)
        self.execution_window.open(exec_id)

        start_time = time.monotonic()
        record_execution_start()
        
        self.journal.append_event(
            session_id=self.session_id,
            event_type="EXECUTION_STARTED",
            execution_id=exec_id
        )

        try:
            await self._run(exec_id, intent, decision)

            # ✅ SUCCESS → reset circuit breaker
            if self._consecutive_failures > 0:
                print("[CIRCUIT] reset after successful execution")
                self._consecutive_failures = 0

            # 🔥 QUAN TRỌNG: RETURN SUCCESS EVENT
            duration = time.monotonic() - start_time
            record_execution_completed(duration)
            return self._build_success(
                intent,
                decision,
                "EXECUTION_COMPLETED"
            )

        except Exception as e:

            # 1️⃣ Log execution failed
            self.journal.append_event(
                session_id=self.session_id,
                event_type="EXECUTION_FAILED",
                execution_id=exec_id,
                error_type="RUNTIME",
                error_message=str(e)
            )

            # 2️⃣ Increment circuit breaker
            self._consecutive_failures += 1
            record_execution_failure()

            self.journal.append_event(
                session_id=self.session_id,
                event_type="CIRCUIT_BREAK_INCREMENT",
                execution_id=exec_id
            )

            print(f"[CIRCUIT] failure count: {self._consecutive_failures}")

            # 3️⃣ Freeze only if threshold reached
            if self._consecutive_failures >= self._failure_threshold:
                print("[CIRCUIT] THRESHOLD REACHED → FREEZE SYSTEM")

                self.execution_state.freeze(
                    f"CIRCUIT_BREAKER: {self._consecutive_failures} consecutive failures"
                )

                self.journal.append_event(
                    session_id=self.session_id,
                    event_type="SYSTEM_FROZEN",
                    freeze_flag=1
                )

            self.execution_lock.abort(str(e), by="orchestrator")
            self.execution_window.force_close(str(e))
            raise

    # ============================================================
    # CORE FLOW
    # ============================================================

    async def _run(self, exec_id, intent, decision):
        run_start = time.monotonic()
        close_count = 0
        open_count = 0

        self.execution_lock.update_phase(
            exec_id,
            ExecutionPhase.CONFIRMING
        )

        positions = self.execution_system.sync_engine.position.get_all()

        plan = self.planner.build_plan(
            positions=positions,
            target=decision.target
        )

        plan.execution_id = exec_id

        # 🔥 PROPAGATE METADATA
        plan.metadata = getattr(intent, "metadata", {})

        # 🔥 STORE METADATA
        self._execution_metadata = getattr(self, "_execution_metadata", {})
        self._execution_metadata[exec_id] = plan.metadata

        print("[TRACE 3] PLAN", plan.metadata)
        print("[TRACE 4] EXEC PLAN", plan.metadata)

        # 🔒 STEP 6 — verify planner
        self.planner_guard.verify_plan(plan, decision.transition)

        for step in plan.steps:
            if step.action == StepAction.CLOSE:
                close_count += 1
            elif step.action == StepAction.OPEN:
                open_count += 1

            await self._execute_step(exec_id, step)

        await self._finalize(exec_id, decision)

        if decision.transition == "REVERSE":
            reverse_duration = time.monotonic() - run_start
            record_reverse_cycle(reverse_duration)

        self._consecutive_failures = 0

    # ============================================================
    # STEP EXECUTION
    # ============================================================

    async def _execute_step(self, exec_id, step):

        self.execution_lock.guard(exec_id)

        if self.execution_state.status != ExecutionStatus.READY:
            raise Exception("EXECUTION NOT READY")

        symbol = step.symbol

        if step.action == StepAction.CLOSE:
            # 🔥 FORCE REFRESH FROM EXCHANGE
            try:
                self.execution_system.exchange.trade.get_positions()
            except:
                pass
            # 🔥 CHECK REAL POSITION BEFORE CLOSE
            positions = self.execution_system.sync_engine.position.get_all()

            current_size = 0.0
            for p in positions:
                if getattr(p, "symbol", None) == symbol:
                    current_size = abs(float(getattr(p, "size", 0.0)))
                    break

            if current_size <= 1e-6:
                print("[ORCHESTRATOR] SKIP CLOSE — already flat")
                return
            # ✅ FIX CRITICAL
            self.execution_lock.update_phase(exec_id, ExecutionPhase.CLOSING)
            side = "SELL" if step.side == TargetSide.LONG else "BUY"

            params = dict(
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=current_size,
                reduceOnly=True
            )

        elif step.action == StepAction.OPEN:
            # ✅ FIX CRITICAL
            self.execution_lock.update_phase(exec_id, ExecutionPhase.OPENING)
            side = "BUY" if step.side == TargetSide.LONG else "SELL"

            params = dict(
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=step.qty,
                reduceOnly=False
            )

        else:
            raise ValueError(f"Unsupported step action: {step.action}")

        # ===== SEND ORDER =====
        client_order_id = f"{exec_id[:8]}_{uuid.uuid4().hex[:12]}"
        key = f"{symbol}-{client_order_id}"

        latency = self.execution_system.sync_engine._latency_buffer.setdefault(key, {})

        metadata = getattr(self, "_execution_metadata", {}).get(exec_id, {})

        latency["metadata"] = metadata

        print("[TRACE LATENCY ATTACH]", key, metadata)
        # 🔥 GET METADATA FROM EXECUTION STORE
        metadata = getattr(self, "_execution_metadata", {}).get(exec_id, {})

        # 🔥 REGISTER METADATA USING CLIENT ORDER ID
        if hasattr(self.execution_system, "register_execution_metadata"):
            self.execution_system.register_execution_metadata(
                client_order_id,
                metadata
            )

        print("[TRACE FINAL CLIENT]", client_order_id, metadata)

        # 1️⃣ SEND ORDER FIRST
        resp = self.execution_system.exchange.trade.place_order(
            execution_id=exec_id,
            newClientOrderId=client_order_id,
            **params
        )
        exchange_order_id = resp.get("orderId")
        if not exchange_order_id:
            raise Exception("Exchange did not return orderId")

        # ✅ FIX — revalidate execution ownership
        self.execution_lock.guard(exec_id)

        # 2️⃣ THEN JOURNAL
        self.journal.append_event(
            session_id=self.session_id,
            event_type="STEP_CLOSE_SENT" 
                if step.action == StepAction.CLOSE 
                else "STEP_OPEN_SENT",
            execution_id=exec_id,
            step=str(step.action),
            side = step.side.name if hasattr(step.side, "name") else step.side,
            quantity=current_size if step.action == StepAction.CLOSE else step.qty,
            order_id=exchange_order_id
        )
        
        await self._wait_position_confirm(exec_id, step)
        print("[ORCHESTRATOR] STEP CONFIRMED")

        await self._wait_sync_reflect(step)
       
        self.journal.append_event(
            session_id=self.session_id,
            event_type="STEP_CLOSE_CONFIRMED" if step.action == StepAction.CLOSE else "STEP_OPEN_CONFIRMED",
            execution_id=exec_id,
            step=str(step.action),
            side = step.side.name if hasattr(step.side, "name") else step.side,
            quantity=current_size if step.action == StepAction.CLOSE else step.qty
        )

    # ============================================================
    # CONFIRM
    # ============================================================

    async def _wait_position_confirm(self, exec_id, step, timeout=15):

        start = asyncio.get_event_loop().time()
        tolerance = 1e-6

        while True:
            self.execution_lock.guard(exec_id)

            try:
                raw_positions = self.execution_system.exchange.trade.get_positions()
                current_size = 0.0

                for p in raw_positions:
                    if p.get("symbol") == step.symbol:
                        amt = float(p.get("positionAmt", 0))
                        if abs(amt) > tolerance:
                            current_size = abs(amt)
                            break

            except Exception as e:
                print("[ORCHESTRATOR] confirm REST error:", e)
                current_size = 0.0

            # ===== OPEN CONFIRM =====
            if step.action == StepAction.OPEN:
                if current_size > tolerance:
                    return

            # ===== CLOSE CONFIRM =====
            if step.action == StepAction.CLOSE:
                if current_size < step.qty:
                    return

            # ===== TIMEOUT =====
            if asyncio.get_event_loop().time() - start > timeout:
                raise Exception(
                    f"CONFIRM TIMEOUT: expected={step.qty}, actual={current_size}"
                )

            await asyncio.sleep(0.2)

    # ============================================================
    async def _wait_sync_reflect(self, step, timeout=5):

        start = asyncio.get_event_loop().time()
        tolerance = 1e-6

        while True:

            # 🔥 CHECK DIRECT FROM EXCHANGE (NOT SYNC)
            try:
                raw_positions = self.execution_system.exchange.trade.get_positions()
                current_size = 0.0

                for p in raw_positions:
                    if p.get("symbol") == step.symbol:
                        amt = float(p.get("positionAmt", 0))
                        if abs(amt) > tolerance:
                            current_size = abs(amt)
                            break

            except Exception as e:
                print("[SYNC REFLECT] REST error:", e)
                current_size = 0.0

            # ===== OPEN confirm =====
            if step.action == StepAction.OPEN:
                if current_size > tolerance:
                    return

            # ===== CLOSE confirm =====
            if step.action == StepAction.CLOSE:
                if current_size <= tolerance:
                    return

            if asyncio.get_event_loop().time() - start > timeout:
                print("[ORCHESTRATOR] SYNC REFLECT SKIP (fallback to exchange truth)")
                return  # 🔥 KHÔNG raise nữa

            await asyncio.sleep(0.2)
    # ============================================================
    # FINALIZE
    # ============================================================

    async def _finalize(self, exec_id, decision):

        self.execution_window.mark_closing(exec_id)

        finalize_ok = True

        try:
            await self.execution_system.supervisor.force_reconcile(exec_id)

            final_positions = (
                self.execution_system.sync_engine.position.get_all()
            )

            final_net = (
                self.execution_system.position_projector.project(
                    final_positions
                )
            )

            # constitutional verification
            self.policy.verify_execution_result(
                decision.target,
                final_net
            )

        except Exception as e:
            finalize_ok = False
            print(
                "[ORCHESTRATOR] finalize reconcile error:",
                e
            )

            # 🔥 journal failure for recovery engine
            self.journal.append_event(
                session_id=self.session_id,
                event_type="EXECUTION_FAILED",
                execution_id=exec_id,
                error_type="FINALIZE_MISMATCH",
                error_message=str(e)
            )

        # =====================================
        # SUCCESS PATH
        # =====================================
        if finalize_ok:
            try:
                self.journal.append_event(
                    session_id=self.session_id,
                    event_type="EXECUTION_COMPLETED",
                    execution_id=exec_id
                )

                self.execution_lock.release(exec_id)

            except Exception as e:
                print("[ORCHESTRATOR] execution release error:", e)

        else:
            print("[ORCHESTRATOR] finalize failed → abort execution")

            try:
                self.execution_lock.abort(
                    reason="FINALIZE_MISMATCH",
                    by="orchestrator"
                )
            except Exception as e:
                print("[ORCHESTRATOR] abort error:", e)

        # window always close
        try:
            self.execution_window.close(exec_id)
        except Exception:
            pass
    # ============================================================
    # UTIL
    # ============================================================

    def _pick_current_position(self, positions):
        if not positions:
            return None
        for p in positions:
            if getattr(p, "qty", 0) != 0:
                return p
        return None

    async def execute(self, intent):
        return await self.submit_intent(intent)
            
         
    def _build_success(self, intent, decision, reason):
        return ExecutionEvent(
            intent_id=intent.intent_id,
            decision=decision.decision.value,
            reason=reason,
            ts=int(time.time() * 1000),
        )

    def _build_refuse(self, intent, reason):
        return ExecutionEvent(
            intent_id=intent.intent_id,
            decision="REFUSED",
            reason=reason,
            ts=int(time.time() * 1000),
        )

    async def handle_intent(self, intent):
        return asyncio.create_task(self.submit_intent(intent))
    
    def health_check(self):

        try:
            state = self.execution_state.status
        except Exception:
            state = "UNKNOWN"

        return {
            "status": str(state),
            "consecutive_failures": getattr(self, "_consecutive_failures", 0)
        }
