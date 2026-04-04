# execution/orchestrator/models.py

from dataclasses import dataclass
from enum import Enum


class TargetSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class StepAction(str, Enum):
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"
    OPEN = "OPEN"


@dataclass
class PositionIntent:
    target_side: TargetSide
    target_size: float
    reason: str
    meta: dict


@dataclass
class ExecutionStep:
    action: StepAction
    side: str
    qty: float
    reduce_only: bool
    symbol: str

@dataclass
class ExecutionPlan:
    steps: list[ExecutionStep]
