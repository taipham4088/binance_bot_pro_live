# execution/reconciliation/report.py

from enum import Enum
from dataclasses import dataclass, field
from typing import List


# =========================
# SEVERITY
# =========================

class DriftSeverity(str, Enum):
    SAFE = "SAFE"
    RECOVERABLE = "RECOVERABLE"
    FATAL = "FATAL"


# =========================
# DRIFT TYPES
# =========================

class DriftType(str, Enum):
    # connection / sync
    MISSING_EVENT = "MISSING_EVENT"
    STALE_STATE = "STALE_STATE"
    RESTART_MID_EXECUTION = "RESTART_MID_EXECUTION"

    # position / order
    GHOST_POSITION = "GHOST_POSITION"
    PHANTOM_LOCAL_POSITION = "PHANTOM_LOCAL_POSITION"
    GHOST_ORDER = "GHOST_ORDER"
    PARTIAL_REVERSE = "PARTIAL_REVERSE"

    # numeric / balance
    MINOR_NUMERIC_DRIFT = "MINOR_NUMERIC_DRIFT"
    BALANCE_INVARIANT_BREAK = "BALANCE_INVARIANT_BREAK"

    # architecture
    EXECUTION_BYPASS = "EXECUTION_BYPASS"
    CORRUPTED_LOCAL_STATE = "CORRUPTED_LOCAL_STATE"


# =========================
# INVARIANTS
# =========================

class InvariantType(str, Enum):
    POSITION_MATCH = "POSITION_MATCH"
    EXPOSURE_MATCH = "EXPOSURE_MATCH"
    ORDER_MATCH = "ORDER_MATCH"
    BALANCE_VALID = "BALANCE_VALID"
    EXECUTION_AUTHORITY = "EXECUTION_AUTHORITY"
    LOCAL_STATE_INTEGRITY = "LOCAL_STATE_INTEGRITY"


# =========================
# REPORT
# =========================

@dataclass
class DriftReport:
    drifts: List[DriftType] = field(default_factory=list)
    broken_invariants: List[InvariantType] = field(default_factory=list)
    severity: DriftSeverity = DriftSeverity.SAFE
    notes: List[str] = field(default_factory=list)

    def is_safe(self) -> bool:
        return self.severity == DriftSeverity.SAFE

    def is_recoverable(self) -> bool:
        return self.severity == DriftSeverity.RECOVERABLE

    def is_fatal(self) -> bool:
        return self.severity == DriftSeverity.FATAL

    def summary(self) -> str:
        parts = []
        if self.drifts:
            parts.append("drifts=" + ",".join(d.value for d in self.drifts))
        if self.broken_invariants:
            parts.append("invariants=" + ",".join(i.value for i in self.broken_invariants))
        if self.notes:
            parts.append("notes=" + " | ".join(self.notes))
        return "; ".join(parts) if parts else "SAFE"

    def has_only_trading_mismatch(self) -> bool:
        """
        True nếu drift chỉ thuộc nhóm mismatch do execution gây ra
        (được phép trong GRACE MODE).
        """
        allowed = {
            DriftType.GHOST_POSITION,
            DriftType.PHANTOM_LOCAL_POSITION,
            DriftType.PARTIAL_REVERSE,
            DriftType.GHOST_ORDER,
        }

        if not self.drifts:
            return False

        return set(self.drifts).issubset(allowed)

from dataclasses import dataclass
from typing import List


@dataclass
class InvariantReport:
    broken_invariants: List["InvariantType"]
    severity: "DriftSeverity"
    notes: List[str]

