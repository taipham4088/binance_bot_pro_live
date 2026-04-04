from execution.reconciliation.report import DriftType, DriftSeverity, InvariantType, InvariantReport

# execution/reconciliation/invariant_engine.py

from execution.reconciliation.report import (
    DriftReport,
    DriftSeverity,
    DriftType,
    InvariantType
)


class InvariantEngine:
    """
    InvariantEngine nhận:
    - local truth
    - exchange truth
    - danh sách drift

    và trả về:
    - invariant nào gãy
    - severity level
    """

    def __init__(self, execution_lock):
        self.execution_lock = execution_lock

    # =========================
    # MAIN
    # =========================

    def check(
        self,
        drifts: list[DriftType],
        require_active_execution: bool = True
    ) -> DriftReport:

        from execution.system.execution_lock import ExecutionState

        # ===== IGNORE STALE WHEN IDLE =====
        if (
            drifts == [DriftType.STALE_STATE]
            and require_active_execution
            and self.execution_lock.state == ExecutionState.IDLE
        ):
            return DriftReport(
                drifts=[],
                broken_invariants=[],
                severity=DriftSeverity.SAFE,
                notes=["ignored stale state while idle"]
            )

        broken: list[InvariantType] = []
        notes: list[str] = []

        # ===== POSITION / EXPOSURE =====
        if DriftType.GHOST_POSITION in drifts:
            broken += [InvariantType.POSITION_MATCH, InvariantType.EXPOSURE_MATCH]
            notes.append("exchange has unknown position")

        if DriftType.PHANTOM_LOCAL_POSITION in drifts:
            broken += [InvariantType.POSITION_MATCH, InvariantType.EXPOSURE_MATCH]
            notes.append("local has phantom position")

        if DriftType.PARTIAL_REVERSE in drifts:
            broken += [InvariantType.POSITION_MATCH, InvariantType.EXPOSURE_MATCH]
            notes.append("local and exchange are opposite side")

        # ===== ORDER =====
        if DriftType.GHOST_ORDER in drifts:
            broken.append(InvariantType.ORDER_MATCH)
            notes.append("exchange has unknown order")

        # ===== BALANCE =====
        if DriftType.BALANCE_INVARIANT_BREAK in drifts:
            broken.append(InvariantType.BALANCE_VALID)
            notes.append("balance invariant broken")

        # ===== EXECUTION AUTHORITY =====
        if DriftType.EXECUTION_BYPASS in drifts:
            broken.append(InvariantType.EXECUTION_AUTHORITY)
            notes.append("execution bypass detected")

        # --- corrupted local state (FATAL) ---
        if DriftType.CORRUPTED_LOCAL_STATE in drifts:
            broken.append(InvariantType.LOCAL_STATE_INTEGRITY)
            severity = DriftSeverity.FATAL
            notes.append("local execution state corrupted")

        # ===== SEVERITY CLASSIFICATION =====

        severity = self._classify_severity(drifts, broken)

        return DriftReport(
            drifts=drifts,
            broken_invariants=broken,
            severity=severity,
            notes=notes
        )

    # =========================
    # SEVERITY LAW
    # =========================

    def _classify_severity(
        self,
        drifts: list[DriftType],
        broken: list[InvariantType]
    ) -> DriftSeverity:

        # Không drift → SAFE
        if not drifts:
            return DriftSeverity.SAFE

        # ===== FATAL CONDITIONS =====

        fatal_drifts = {
            DriftType.GHOST_POSITION,
            DriftType.PHANTOM_LOCAL_POSITION,
            DriftType.PARTIAL_REVERSE,
            DriftType.EXECUTION_BYPASS,
            DriftType.BALANCE_INVARIANT_BREAK,
        }

        for d in drifts:
            if d in fatal_drifts:
                return DriftSeverity.FATAL

        # ===== RECOVERABLE CONDITIONS =====

        recoverable_drifts = {
            DriftType.MISSING_EVENT,
            DriftType.STALE_STATE,
            DriftType.GHOST_ORDER,
            DriftType.MINOR_NUMERIC_DRIFT,
            DriftType.RESTART_MID_EXECUTION,
        }

        for d in drifts:
            if d in recoverable_drifts:
                return DriftSeverity.RECOVERABLE

        # fallback an toàn
        if broken:
            return DriftSeverity.FATAL

        return DriftSeverity.SAFE
