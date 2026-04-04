from typing import Optional
from copy import deepcopy

from backend.execution.types.execution_state import ExecutionState
from backend.execution.emission.snapshot_builder import build_snapshot
from backend.execution.emission.delta_builder import build_delta


class StateEmitter:
    """
    Emit SNAPSHOT / DELTA
    Does NOT know WS / UI
    """

    def __init__(self):
        self._last_state: Optional[ExecutionState] = None

    def emit(self, current_state: ExecutionState) -> dict:
        """
        Return message:
          - SNAPSHOT (first time)
          - DELTA (after)
        """

        if self._last_state is None:
            self._last_state = deepcopy(current_state)
            return {
                "type": "SNAPSHOT",
                "payload": build_snapshot(current_state),
            }

        delta = build_delta(self._last_state, current_state)
        self._last_state = deepcopy(current_state)

        return {
            "type": "DELTA",
            "payload": delta,
        }
