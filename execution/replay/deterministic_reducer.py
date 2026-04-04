# execution/replay/deterministic_reducer.py

from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class CanonicalReplayState:
    freeze_flag: bool = False
    circuit_consecutive_failures: int = 0
    execution_state: str = "IDLE"   # IDLE | RUNNING
    active_execution_id: Optional[str] = None
    last_order_id: Optional[str] = None


class DeterministicReducer:
    """
    Pure deterministic reducer.

    Guarantees:
    - No side effects
    - No exchange calls
    - No DB calls
    - Deterministic replay from journal events
    """

    CIRCUIT_THRESHOLD = 3

    def rebuild(self, events: List[Dict[str, Any]]) -> CanonicalReplayState:
        state = CanonicalReplayState()

        last_id = None

        for event in events:
            event_id = event["id"]

            # Strict order enforcement (defensive)
            if last_id is not None and event_id <= last_id:
                raise Exception("Journal order corrupted (non-monotonic id)")
            last_id = event_id

            event_type = event.get("event_type")
            execution_id = event.get("execution_id")
            order_id = event.get("order_id")
            freeze_flag = event.get("freeze_flag", 0)

            # ==============================
            # Circuit logic
            # ==============================
            if event_type == "CIRCUIT_BREAK_INCREMENT":
                state.circuit_consecutive_failures += 1

            # ==============================
            # Freeze logic
            # ==============================
            if event_type == "SYSTEM_FROZEN":
                state.freeze_flag = True

            if event_type == "SYSTEM_UNFROZEN":
                state.freeze_flag = False
                state.circuit_consecutive_failures = 0

            # Defensive: if freeze_flag stored on event
            if freeze_flag == 1:
                state.freeze_flag = True

            # ==============================
            # Execution lifecycle
            # ==============================
            if event_type == "EXECUTION_STARTED":
                state.execution_state = "RUNNING"
                state.active_execution_id = execution_id

            if event_type in ("EXECUTION_COMPLETED", "EXECUTION_FAILED"):
                state.execution_state = "IDLE"
                state.active_execution_id = None

            # ==============================
            # Order tracking
            # ==============================
            if order_id:
                state.last_order_id = order_id

            # ==============================
            # Circuit threshold auto-freeze
            # ==============================
            if state.circuit_consecutive_failures >= self.CIRCUIT_THRESHOLD:
                state.freeze_flag = True

        return state
