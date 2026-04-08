# backend/core/execution_models.py

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import time


# =========================
# PLAN ACTION
# =========================

class PlanAction(str, Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    REDUCE = "REDUCE"
    NOOP = "NOOP"
    BLOCK = "BLOCK"


# =========================
# POSITION SIDE
# =========================

class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


# =========================
# EXECUTION PLAN
# =========================

@dataclass(frozen=True)
class ExecutionPlan:
    action: PlanAction
    symbol: Optional[str]
    side: Optional[PositionSide]
    quantity: float
    reduce_only: bool
    reason: str
    source: str
    timestamp: int
    metadata: Optional[Dict[str, Any]] = None


# =========================
# EXECUTION DECISION
# =========================

@dataclass(frozen=True)
class ExecutionDecision:
    plan: ExecutionPlan


# =========================
# EXECUTION EVENT
# =========================

@dataclass
class ExecutionEvent:
    intent_id: str
    decision: str
    reason: str
    ts: int

    symbol: Optional[str] = None
    side: Optional[str] = None
    size: Optional[float] = None

    source: Optional[str] = None
    position: Optional[dict] = None
    payload: Optional[dict] = None


# =========================
# EXECUTION INTENT
# =========================

@dataclass
class ExecutionIntent:
    intent_id: str
    symbol: str
    side: Optional[str]
    qty: float
    price: Optional[float]
    type: str
    ts: int


# =========================
# EXECUTION RESULT
# =========================

@dataclass
class ExecutionResult:
    success: bool
    event: Optional[ExecutionEvent]
    error: Optional[str] = None