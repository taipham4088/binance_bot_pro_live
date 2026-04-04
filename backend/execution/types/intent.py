from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class Intent:
    intent_id: str
    session_id: str
    source: str          # strategy | manual | system
    type: str            # open_long | open_short | close | reduce
    payload: Dict[str, Any]
    timestamp: int
