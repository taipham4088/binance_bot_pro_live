from typing import Dict, Any, List, Optional
from backend.execution.divergence.divergence_types import DivergenceType


class DivergenceDetector:
    """
    Compare LIVE vs REPLAY at SAME timeline_index
    """

    def compare_step(
        self,
        index: int,
        live_event: Dict[str, Any],
        replay_event: Dict[str, Any],
        live_state: Dict[str, Any],
        replay_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Return:
          {
            type: DivergenceType,
            reason: str,
            index: int,
            details: dict
          }
        """

        # --------------------------------------------------
        # ORDER (index mismatch)
        # --------------------------------------------------
        if live_event.get("index") != replay_event.get("index"):
            return self._result(
                DivergenceType.ORDER,
                "timeline_index mismatch",
                index,
                {
                    "live_index": live_event.get("index"),
                    "replay_index": replay_event.get("index"),
                },
            )

        # --------------------------------------------------
        # DECISION
        # --------------------------------------------------
        live_decision = live_event.get("decision", {})
        replay_decision = replay_event.get("decision", {})

        if live_decision != replay_decision:
            return self._result(
                DivergenceType.DECISION,
                "decision mismatch",
                index,
                {
                    "live_decision": live_decision,
                    "replay_decision": replay_decision,
                },
            )

        # --------------------------------------------------
        # STATE (compare minimal invariant fields)
        # --------------------------------------------------
        keys = [
            "execution_state",
            "position",
            "last_decision",
        ]

        state_diff = {}
        for k in keys:
            if live_state.get(k) != replay_state.get(k):
                state_diff[k] = {
                    "live": live_state.get(k),
                    "replay": replay_state.get(k),
                }

        if state_diff:
            return self._result(
                DivergenceType.STATE,
                "state mismatch",
                index,
                state_diff,
            )

        return self._result(DivergenceType.NONE, "no divergence", index, {})

    def _result(
        self,
        dtype: DivergenceType,
        reason: str,
        index: int,
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "type": dtype,
            "reason": reason,
            "index": index,
            "details": details,
        }
