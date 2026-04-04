from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class ExecutionContext:
    authority: str
    position: Dict[str, Any]
    risk: Dict[str, Any]
    health: str
    kill_switch: bool
