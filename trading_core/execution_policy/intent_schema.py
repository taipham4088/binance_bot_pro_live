from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict


class IntentType(str, Enum):
    SET_POSITION = "SET_POSITION"
    SET_FLAT = "SET_FLAT"
    EMERGENCY = "EMERGENCY"


@dataclass(frozen=True)
class ExecutionIntent:
    intent_id: str
    symbol: str
    type: IntentType
    side: Optional[str] = None
    qty: Optional[float] = None
    source: str = "strategy"
    metadata: Dict = field(default_factory=dict)

    def validate_schema(self):
        if not self.intent_id:
            raise ValueError("intent_id required")
        if not self.symbol:
            raise ValueError("symbol required")

        if self.type == IntentType.SET_POSITION:
            if self.side not in ("LONG", "SHORT"):
                raise ValueError("SET_POSITION requires side LONG/SHORT")
            if self.qty is None:
                raise ValueError("SET_POSITION requires qty")

        if self.type == IntentType.SET_FLAT:
            if self.qty not in (None, 0):
                raise ValueError("SET_FLAT must not carry qty")
