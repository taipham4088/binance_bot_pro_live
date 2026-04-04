from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


class SeverityLevel(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ReactionType(str, Enum):
    NONE = "NONE"        # LOG / no-op
    NOTIFY = "NOTIFY"
    FREEZE = "FREEZE"
    ESCALATE = "ESCALATE"   # always implies FREEZE


@dataclass(frozen=True)
class InvariantViolation:
    name: str
    description: str
    severity: SeverityLevel


@dataclass(frozen=True)
class ReactionDecision:
    """
    THE ONLY OUTPUT of Phase 4.5
    Signal-only, no execution authority.
    """
    reaction: ReactionType
    severity: SeverityLevel

    reason: str
    invariants: List[InvariantViolation] = field(default_factory=list)

    freeze_execution: bool = False
    notify_human: bool = False
    escalate_human: bool = False

    reconciliation_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
