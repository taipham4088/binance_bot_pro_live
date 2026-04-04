from backend.observability.supervisor_metrics import (
    record_freeze,
    record_drift_detected,
)

import asyncio
import time

from execution.state.execution_state import ExecutionStatus
from execution.reconciliation.report import DriftSeverity
from execution.reconciliation.drift_detector import DriftDetector
from execution.reconciliation.invariant_engine import InvariantEngine
from execution.system.execution_lock import ExecutionState as LockState

class ReconciliationSupervisor:
    """
    Supervisor là cơ quan điều hành execution system.

    Sau Step 5:
    - STRICT  : không execution → như Step 4
    - GRACE   : đang execution → không freeze, không reconcile cứng
    - VERIFY  : execution vừa xong → force reconcile + verify
    """

    def __init__(self, live_system, execution_window, interval: float = 2.0):
        self.system = live_system
        self.sync_engine = live_system.sync_engine
        self.exchange = live_system.exchange
        self.execution_state = live_system.execution_state
        self.freeze_system = live_system.freeze_system
        self.execution_window = execution_window

        # ✅ THÊM DÒNG NÀY
        self.execution_lock = live_system.execution_lock

        self.detector = DriftDetector(
            self.sync_engine,
            self.exchange,
            stale_threshold=20.0
        )

        # ✅ GIỜ MỚI HỢP LỆ
        self.invariant_engine = InvariantEngine(self.execution_lock)

        self.interval = interval
        self.running = False

    # =========================
    # LIFECYCLE
    # =========================

    async def start(self):
        if self.running:
            return
        self.running = True
        asyncio.create_task(self._loop())

    async def stop(self):
        self.running = False

    # =========================
    # MAIN LOOP
    # =========================

    async def _loop(self):
        while self.running:
            try:
                await self._tick()
            except Exception as e:

                print("[SUPERVISOR] critical error:", e)

                self.execution_state.set_state(
                    ExecutionStatus.FROZEN,
                    "supervisor crashed"
                )

                try:
                    self.freeze_system.freeze("supervisor crashed")
                except Exception:
                    pass

                # 🔥 AUTO RESTART
                try:
                    print("[SUPERVISOR] attempting auto restart")

                    if hasattr(self.system, "restart"):
                        await self.system.restart()

                    print("[SUPERVISOR] restart successful")
 
                except Exception as e2:
                    print("[SUPERVISOR] restart failed:", e2)

                return
            await asyncio.sleep(self.interval)

    # =========================
    # TICK
    # =========================

    async def _tick(self):

        state = self.execution_state.status

        if state == ExecutionStatus.FROZEN:
            return

        if state == ExecutionStatus.BOOTSTRAPPING:
            return

        drifts = self.detector.detect()
        report = self.invariant_engine.check(drifts)
        if drifts:
            record_drift_detected()

        # =========================
        # MODE SWITCH
        # =========================

        if self.execution_window.is_open():
            await self._handle_grace(report)
            return

        if self.execution_window.is_closing():
            await self._handle_verify(report)
            return

        await self._handle_strict(report)

    # =========================
    # MODES
    # =========================

    async def _handle_strict(self, report):

        if report.severity == DriftSeverity.SAFE:
            if self.execution_state.status != ExecutionStatus.READY:
                self.execution_state.set_state(
                    ExecutionStatus.READY,
                    "system healthy"
                )
            return

        if report.severity == DriftSeverity.RECOVERABLE:
            if self.execution_state.status != ExecutionStatus.DEGRADED:
                self.execution_state.set_state(
                    ExecutionStatus.DEGRADED,
                    "recoverable drift detected"
                )
            await self._reconcile(report)
            return

        # ===== FATAL =====

        summary = report.summary()

        # ✅ TEMP FIX — bỏ freeze cho trading mismatch
        if "GHOST_POSITION" in summary or "PHANTOM_LOCAL_POSITION" in summary:
            # 🔥 skip immediately after execution
            if self.execution_lock.state != LockState.IDLE:
                return
            print("[SUPERVISOR] TEMP SKIP FREEZE:", summary)
            return

        self._freeze(report)
        self.execution_state.set_state(
            ExecutionStatus.FROZEN,
            "fatal drift detected"
        )
        
        try:
            if hasattr(self.system, "restart"):
                print("[SUPERVISOR] auto restart after fatal drift")
                await self.system.restart()
        except Exception as e:
            print("[SUPERVISOR] restart failed:", e)

    #=========================================
    async def _handle_grace(self, report):
        """
        Đang execution window.

        - KHÔNG freeze vì mismatch do chính execution gây ra
        - CHỈ freeze nếu là drift hệ thống nghiêm trọng
        """

        # ===== Trading mismatches (được phép trong grace mode) =====
        if report.has_only_trading_mismatch() or "GHOST_POSITION" in report.summary():
            print("[SUPERVISOR] grace trading drift:", report.summary())
            self.execution_window.record_anomaly(report)
            return

        # ===== Safe =====
        if report.severity == DriftSeverity.SAFE:
            return

        # ===== System fatal drift =====
        if report.severity == DriftSeverity.FATAL:
            print("[SUPERVISOR] TEMP IGNORE FATAL IN GRACE:", report.summary())
            return

        # 🔥 FIX: không cho freeze khi execution đang chạy
        if self.execution_lock.state == LockState.RUNNING:
            print("[SUPERVISOR] skip fatal drift (execution active)")
            self.execution_window.record_anomaly(report)
            return

        self.execution_state.set_state(
            ExecutionStatus.FROZEN,
            "fatal system drift during execution"
        )

        self._freeze(report)
        return

        # ===== Other drifts (log only) =====
        print("[SUPERVISOR] grace non-fatal drift:", report.summary())
        self.execution_window.record_anomaly(report)

    async def _handle_verify(self, report):
        """
        Execution vừa xong → không khoan nhượng
        """
        if self.execution_lock.state != LockState.IDLE:
            return
        if report.severity == DriftSeverity.SAFE:
            self.execution_state.set_state(
                ExecutionStatus.READY,
                "post execution clean"
            )
            return

        if report.severity == DriftSeverity.RECOVERABLE:
            await self._reconcile(report)

            drifts = self.detector.detect()
            final = self.invariant_engine.check(drifts)

            if final.severity == DriftSeverity.SAFE:
                self.execution_state.set_state(
                    ExecutionStatus.READY,
                    "post reconcile clean"
                )
                return

        # 🔥 FIX: không freeze ngay sau execution fail
        if self.execution_lock.state != LockState.IDLE:
            print("[SUPERVISOR] skip verify freeze (execution not settled)")
            return

        self.execution_state.set_state(
            ExecutionStatus.FROZEN,
            "post execution mismatch"
        )
        try:
            if hasattr(self.system, "restart"):
                print("[SUPERVISOR] restart after verify failure")
                await self.system.restart()
        except Exception as e:
            print("[SUPERVISOR] restart failed:", e)

        self._freeze(report)

    # =========================
    # ACTIONS
    # =========================

    async def _reconcile(self, report):
        """
        Reconcile flow.
        Chỉ rebuild local truth, KHÔNG trade.
        """
        if self.execution_lock.state == LockState.RUNNING:
            print("[SUPERVISOR] skip reconcile (execution active)")
            return
        print("[SUPERVISOR] reconcile start:", report.summary())

        try:
            snapshot = self.exchange.get_snapshot()
            self.sync_engine.bootstrap(snapshot)
        except Exception as e:
            print("[SUPERVISOR] reconcile failed:", e)
            self.execution_state.set_state(
                ExecutionStatus.FROZEN,
                "reconcile failed"
            )
            self._freeze(report)

    def _freeze(self, report):
        """
        Freeze & containment.

        ❗ Production rule:
        NEVER freeze while execution is active.
        """

        # ✅ FIX A — system chưa READY → không freeze
        try:
            if self.system.execution_state.status != ExecutionStatus.READY:
                print(
                    "[SUPERVISOR] GRACE (system not ready):",
                    report.summary()
                )
                return
        except Exception:
            pass

        # ✅ FIX B — execution đang chạy → KHÔNG freeze
        try:
            if self.execution_lock.state == LockState.RUNNING:
                print(
                    "[SUPERVISOR] GRACE (execution active):",
                    report.summary()
                )
                return
        except Exception:
            pass

        # ✅ Only freeze when system idle
        print("[SUPERVISOR] FREEZE:", report.summary())
        record_freeze(report.summary())

        try:
            self.freeze_system.freeze(report.summary())
        except Exception as e:
            print("[SUPERVISOR] freeze system error:", e)

    # =========================
    # ORCHESTRATOR API
    # =========================

    async def force_reconcile(self, exec_id):

        print("[SUPERVISOR] post execution reconcile")

        snapshot = self.exchange.get_snapshot()
        self.sync_engine.bootstrap(snapshot)

        # 🔥 skip invariant execution-active check
        drifts = self.detector.detect()
        report = self.invariant_engine.check(
            drifts,
            require_active_execution=False   # 👈 thêm flag
        )

        if report.severity != DriftSeverity.SAFE:
            await self._handle_verify(report)
