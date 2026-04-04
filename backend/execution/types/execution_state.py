from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class ExecutionState:
    meta: Dict[str, Any]

    authority: str       # paper | live-readonly | live-trade
    health: str          # normal | degraded | critical
    execution_state: str # IDLE | OPENING | OPEN | REDUCING | CLOSING | BLOCKED | ERROR

    position: Dict[str, Any]
    risk: Dict[str, Any]
    last_decision: Dict[str, Any]
