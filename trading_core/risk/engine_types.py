from dataclasses import dataclass
from enum import Enum
from typing import Optional

from trading_core.risk.reason import RiskReason


class RiskVerdict(str, Enum):
    ALLOW = "ALLOW"
    REFUSE = "REFUSE"
    FREEZE = "FREEZE"


@dataclass
class RiskDecision:
    verdict: RiskVerdict
    reason: Optional[RiskReason]
    detail: Optional[str] = None
