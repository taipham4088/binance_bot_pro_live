# =====================================================================
# ⚠ LEGACY DECISION ENGINE – NOT USED IN PRODUCTION FLOW
#
# This module belongs to the old execution decision engine.
# The current production architecture uses:
#   - backend/core/*
#   - execution/live_execution_system.py
#
# DO NOT import this module into backend/core or WS flow.
# =====================================================================
from typing import Optional
from time import time

from backend.execution.orchestrator.execution_orchestrator import ExecutionOrchestrator
from backend.execution.orchestrator.execution_context import ExecutionContext
from backend.execution.types.intent import Intent
from backend.execution.types.execution_state import ExecutionState
from backend.execution.decision.decision_types import ExecutionPlanType
from backend.execution.state_machine.state_transition import transition_state
from backend.execution.timeline.timeline_event import TimelineEvent
from backend.execution.adapter.paper_adapter import PaperExecutionAdapter
from backend.execution.adapter.live_adapter_base import LiveAdapterBase
from backend.execution.divergence.divergence_detector import DivergenceDetector
from backend.execution.emission.state_emitter import StateEmitter


def _now_ms() -> int:
    return int(time() * 1000)


class TimelineEngine:
    """
    TimelineEngine
    - Phase 2: Decision + State + Timeline (no adapter)
    - Phase 3.1: Paper execution + Live shadow + Divergence
    """

    def __init__(
        self,
        orchestrator: ExecutionOrchestrator,
        initial_state: ExecutionState,
        context: ExecutionContext,
        *,
        paper_adapter: Optional[PaperExecutionAdapter] = None,
        live_adapter: Optional[LiveAdapterBase] = None,
        divergence_detector: Optional[DivergenceDetector] = None,
        emitter: Optional[StateEmitter] = None,
    ):
        self._orchestrator = orchestrator
        self._context = context

        # Phase 2 baseline
        self._state: ExecutionState = initial_state

        # Phase 3.1 optional components
        self._paper_adapter = paper_adapter
        self._live_adapter = live_adapter
        self._divergence_detector = divergence_detector
        self._emitter = emitter

        self._index: int = initial_state.meta.get("timeline_index", 0)

    # --------------------------------------------------
    # CORE STEP (AUTO SWITCH MODE)
    # --------------------------------------------------
    def step(self, intent: Intent, replay_event: Optional[TimelineEvent] = None):
        """
        One timeline step.
        - Phase 2: decision + state transition only
        - Phase 3.1: paper + shadow + divergence
        """

        # ----------------------------
        # 1. DECISION
        # ----------------------------
        plan = self._orchestrator.decide(intent, self._context)

        prev_state = self._state

        # ----------------------------
        # 2. EXECUTION MODE SWITCH
        # ----------------------------
        if self._paper_adapter is not None:
            # ===== STAGE 3.1 =====
            new_state = self._paper_adapter.execute(plan, prev_state)
        else:
            # ===== PHASE 2 =====
            new_state = prev_state

        # ----------------------------
        # 3. STATE MACHINE
        # ----------------------------
        next_execution_state = transition_state(
            current_state=prev_state.execution_state,
            execution_plan=ExecutionPlanType(plan.plan),
        )
        new_state.execution_state = next_execution_state

        # ----------------------------
        # 4. TIMELINE META
        # ----------------------------
        self._index += 1
        new_state.meta["timeline_index"] = self._index
        new_state.meta["timestamp"] = _now_ms()

        new_state.last_decision = {
            "plan": plan.plan,
            "reason": plan.reason,
            "source": plan.source,
            "timestamp": plan.timestamp,
        }

        self._state = new_state

        event = TimelineEvent(
            index=self._index,
            input=intent,
            decision={
                "plan": plan.plan,
                "execution_state": new_state.execution_state,
            },
            timestamp=_now_ms(),
        )

        # ----------------------------
        # 5. LIVE SHADOW (OPTIONAL)
        # ----------------------------
        shadow = None
        if self._live_adapter is not None:
            shadow = self._live_adapter.execute(plan, self._state)

        # ----------------------------
        # 6. DIVERGENCE (OPTIONAL)
        # ----------------------------
        if (
            replay_event is not None
            and self._divergence_detector is not None
        ):
            div = self._divergence_detector.compare_step(
                index=self._index,
                live_event=event.__dict__,
                replay_event=replay_event.__dict__,
                live_state=self._state.__dict__,
                replay_state=replay_event.decision,
            )
            if div["type"] != "none":
                raise RuntimeError(f"DIVERGENCE DETECTED: {div}")

        # ----------------------------
        # 7. EMIT (OPTIONAL)
        # ----------------------------
        emit = None
        if self._emitter is not None:
            emit = self._emitter.emit(self._state)

        # Phase 3.1 runtime data is kept internally
        # to preserve backward compatibility with Phase 2
        self._last_emit = emit
        self._last_shadow = shadow

        # BACKWARD COMPAT:
        # step() MUST return TimelineEvent
        return event

    # --------------------------------------------------
    # READ ONLY
    # --------------------------------------------------
    def current_state(self) -> ExecutionState:
        return self._state

    def timeline_index(self) -> int:
        return self._index
