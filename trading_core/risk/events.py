from dataclasses import dataclass
from enum import Enum
from typing import Optional
import time

from trading_core.risk.state import RiskState
from trading_core.risk.reason import RiskReason


class RiskEventType(str, Enum):
    STATE_UPDATE = "STATE_UPDATE"
    DAILY_RESET = "DAILY_RESET"

    DAILY_STOP_TRIGGERED = "DAILY_STOP_TRIGGERED"
    DD_BLOCK_TRIGGERED = "DD_BLOCK_TRIGGERED"

    LIMIT_UPDATED = "LIMIT_UPDATED"
    FREEZE = "FREEZE"
    UNFREEZE = "UNFREEZE"


@dataclass
class RiskEvent:
    ts: float
    type: RiskEventType
    snapshot: RiskState
    reason: Optional[RiskReason] = None

    @staticmethod
    def now(event_type: RiskEventType,
            snapshot: RiskState,
            reason: Optional[RiskReason] = None) -> "RiskEvent":
        return RiskEvent(
            ts=time.time(),
            type=event_type,
            snapshot=snapshot,
            reason=reason
        )
