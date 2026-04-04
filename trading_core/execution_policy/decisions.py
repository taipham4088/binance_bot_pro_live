from enum import Enum
from dataclasses import dataclass


class PolicyDecisionType(str, Enum):
    ALLOW = "ALLOW"
    REFUSE = "REFUSE"
    FREEZE = "FREEZE"


@dataclass(frozen=True)
class PolicyDecision:
    decision: PolicyDecisionType
    reason: str
    current: object
    target: object | None = None
    transition: str | None = None
