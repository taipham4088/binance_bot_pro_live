# execution/reconciliation/restart_guard.py

from execution.state.execution_state import ExecutionStatus
from execution.reconciliation.report import DriftSeverity
from execution.reconciliation.drift_detector import DriftDetector
from execution.reconciliation.invariant_engine import InvariantEngine


class RestartGuard:
    """
    RestartGuard chịu trách nhiệm:
    - kiểm tra hệ ngay khi start
    - rebuild local truth
    - detect drift
    - check invariant
    - set execution state ban đầu
    """

    def __init__(self, live_system):
        self.system = live_system
        self.sync_engine = live_system.sync_engine
        self.exchange = live_system.exchange
        self.execution_state = live_system.execution_state

        # 👇 thêm dòng này cho sạch kiến trúc
        self.execution_lock = live_system.execution_lock

        self.detector = DriftDetector(self.sync_engine, self.exchange)
        self.invariant_engine = InvariantEngine(self.execution_lock)
    # =========================
    # MAIN
    # =========================

    def run(self):
        """
        Chạy đúng 1 lần khi system start.
        """

        # 1. Vào bootstrapping
        self.execution_state.set_state(
            ExecutionStatus.BOOTSTRAPPING,
            "system restart"
        )

        # 2. Pull snapshot
        snapshot = self.exchange.get_snapshot()

        # 3. Rebuild local truth
        self.sync_engine.bootstrap(snapshot)

        # 4. Detect drift
        drifts = self.detector.detect()

        # 5. Check invariant
        report = self.invariant_engine.check(drifts)

        # 6. Decide state
        if report.severity == DriftSeverity.SAFE:
            self.execution_state.set_state(
                ExecutionStatus.SYNCING,
                "restart clean"
            )
            return report

        if report.severity == DriftSeverity.RECOVERABLE:
            self.execution_state.set_state(
                ExecutionStatus.DEGRADED,
                "restart needs reconcile"
            )
            return report

        # 7. Fatal → freeze
        self.execution_state.set_state(
            ExecutionStatus.FROZEN,
            "fatal state on restart"
        )

        self.system.freeze_system.freeze(report.summary())

        return report
