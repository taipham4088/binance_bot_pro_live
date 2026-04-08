# backend/core/session_runtime.py
from backend.core.execution_orchestrator import ExecutionIntent
from backend.core.execution_orchestrator import ExecutionOrchestrator
from backend.core.execution_timeline import (
    ExecutionTimeline,
    make_initial_state,
    LastDecision,
)
from backend.core.state_hub import StateHub

import time


class SessionRuntime:
    """
    1 session = 1 execution brain + 1 timeline
    """

    def __init__(
        self,
        *,
        session_id: str,
        mode: str,
        authority: str,
        health: str,
        statehub: StateHub,
    ):
        self.session_id = session_id
        self.statehub = statehub
        self.orchestrator = ExecutionOrchestrator()

        initial_state = make_initial_state(
            session_id=session_id,
            mode=mode,
            authority=authority,
            health=health,
        )

        self.timeline = ExecutionTimeline(initial_state)

    # ---------- PUBLIC ----------

    async def start(self):
        """
        Emit SNAPSHOT khi session start
        """
        snapshot = self.timeline.snapshot()
        await self.statehub.emit_snapshot(self.session_id, snapshot)

    def build_execution_intent(self, ws_intent):
        """
        Convert WS Intent → Core ExecutionIntent
        """
        payload = ws_intent.payload or {}

        action_map = {
            "OPEN_LONG": "open_long",
            "OPEN_SHORT": "open_short",
            "CLOSE": "close",
            "REDUCE": "reduce",
        }

        action = action_map.get(ws_intent.type.upper())

        if not action:
            raise ValueError(f"Unsupported intent type: {ws_intent.type}")

        return ExecutionIntent(
            action=action,
            symbol=payload.get("symbol"),
            size=payload.get("size"),
            source=ws_intent.source,
        )

    async def handle_intent(
        self,
        *,
        authority,
        position,
        risk,
        health,
        intent,
    ):
        """
        Nhận intent → orchestrator → timeline → WS
        """

        decision = self.orchestrator.evaluate(
            authority=authority,
            position=position,
            risk=risk,
            health=health,
            intent=intent,
        )
        print(
            "[DECISION BEFORE EXEC]",
            type(decision),
            getattr(decision.plan, "metadata", None),
        )

        last_decision = LastDecision(
            plan=decision.plan,
            reason=decision.reason,
            source=decision.source,
            timestamp=decision.timestamp,
        )

        delta = self.timeline.step(last_decision)
        await self.statehub.emit_delta(self.session_id, delta)
