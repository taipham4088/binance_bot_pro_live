# backend/core/execution_timeline.py

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, Any, Optional
import time
import jsonpatch

from backend.core.execution_models import PlanAction


# ===== ENUMS =====

class ExecutionState(str, Enum):
    IDLE = "IDLE"
    OPENING = "OPENING"
    OPEN = "OPEN"
    REDUCING = "REDUCING"
    CLOSING = "CLOSING"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


# ===== DATA MODELS =====

@dataclass
class Meta:
    session_id: str
    mode: str
    timeline_index: int
    timestamp: int


@dataclass
class Position:
    side: str
    size: float
    entry_price: float = 0.0


@dataclass
class Risk:
    max_loss: float = 0.0
    max_size: float = 0.0
    breach: bool = False
    kill_switch: bool = False


@dataclass
class LastDecision:
    plan: Any          # ExecutionPlan object (new model)
    reason: str
    source: str
    timestamp: int


@dataclass
class ExecutionStateModel:
    meta: Meta
    authority: str
    health: str
    execution_state: ExecutionState
    position: Position
    risk: Risk
    last_decision: Optional[LastDecision] = None


# ===== TIMELINE ENGINE =====

class ExecutionTimeline:

    def __init__(self, initial_state: ExecutionStateModel):
        self._state = initial_state
        self._last_snapshot = self._serialize_state(initial_state)
        self._timeline_index = initial_state.meta.timeline_index

    # ----- PUBLIC API -----

    def snapshot(self) -> Dict[str, Any]:
        self._last_snapshot = self._serialize_state(self._state)
        return self._last_snapshot

    def step(self, decision: LastDecision) -> Dict[str, Any]:

        prev_state = self._serialize_state(self._state)

        self._timeline_index += 1
        self._state.meta.timeline_index = self._timeline_index
        self._state.meta.timestamp = decision.timestamp

        self._state.last_decision = decision

        # 🔥 UNIFIED CONTRACT
        self._apply_state_transition(decision.plan.action)

        next_state = self._serialize_state(self._state)

        patch = jsonpatch.make_patch(prev_state, next_state)
        return {
            "type": "DELTA",
            "timeline_index": self._timeline_index,
            "timestamp": decision.timestamp,
            "patch": patch.patch,
        }

    # ----- FILL HANDLING (PRODUCTION UPGRADE) -----

    def apply_fill(self, *, side: str, filled_qty: float, price: float = 0.0) -> Dict[str, Any]:

        prev_state = self._serialize_state(self._state)

        if filled_qty <= 0:
            return prev_state

        position = self._state.position

        # OPENING fill
        if self._state.execution_state == ExecutionState.OPENING:

            position.side = side
            position.size += filled_qty
            position.entry_price = price

            # Transition to OPEN
            self._state.execution_state = ExecutionState.OPEN

        # REDUCING fill
        elif self._state.execution_state == ExecutionState.REDUCING:
 
            position.size -= filled_qty
  
            if position.size <= 0:
                position.size = 0
                position.side = "flat"
                self._state.execution_state = ExecutionState.IDLE

        # CLOSING fill
        elif self._state.execution_state == ExecutionState.CLOSING:

            position.size -= filled_qty

            if position.size <= 0:
                position.size = 0
                position.side = "flat"
                self._state.execution_state = ExecutionState.IDLE

        next_state = self._serialize_state(self._state)

        patch = jsonpatch.make_patch(prev_state, next_state)

        return {
            "type": "DELTA",
            "timeline_index": self._state.meta.timeline_index,
            "timestamp": int(time.time() * 1000),
            "patch": patch.patch,
        }

    # ----- INTERNALS -----

    def _apply_state_transition(self, action: PlanAction):

        s = self._state.execution_state

        if action == PlanAction.NOOP:
            return

        if action == PlanAction.BLOCK:
            self._state.execution_state = ExecutionState.BLOCKED
            return

        if s == ExecutionState.IDLE:
            if action == PlanAction.OPEN:
                self._state.execution_state = ExecutionState.OPENING
                return

        if s == ExecutionState.OPEN:
            if action == PlanAction.REDUCE:
                self._state.execution_state = ExecutionState.REDUCING
                return
            if action == PlanAction.CLOSE:
                self._state.execution_state = ExecutionState.CLOSING
                return

        self._state.execution_state = ExecutionState.ERROR

    def _serialize_state(self, state: ExecutionStateModel) -> Dict[str, Any]:

        def normalize(obj):
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, dict):
                return {k: normalize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [normalize(v) for v in obj]
            return obj

        raw = asdict(state)
        return normalize(raw)


# ===== HELPERS =====

def make_initial_state(
    *,
    session_id: str,
    mode: str,
    authority: str,
    health: str,
) -> ExecutionStateModel:

    now = int(time.time() * 1000)

    return ExecutionStateModel(
        meta=Meta(
            session_id=session_id,
            mode=mode,
            timeline_index=0,
            timestamp=now,
        ),
        authority=authority,
        health=health,
        execution_state=ExecutionState.IDLE,
        position=Position(side="flat", size=0.0),
        risk=Risk(),
        last_decision=None,
    )
