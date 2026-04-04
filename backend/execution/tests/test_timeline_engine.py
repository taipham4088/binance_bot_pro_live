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
from backend.execution.timeline.timeline_engine import TimelineEngine
from backend.execution.orchestrator.execution_orchestrator import ExecutionOrchestrator
from backend.execution.orchestrator.execution_context import ExecutionContext
from backend.execution.types.execution_state import ExecutionState
from backend.execution.types.intent import Intent


def make_intent():
    return Intent(
        intent_id="i1",
        session_id="s1",
        source="manual",
        type="open_long",
        payload={},
        timestamp=0,
    )


def make_state():
    return ExecutionState(
        meta={"timeline_index": 0, "timestamp": 0},
        authority="live-trade",
        health="normal",
        execution_state="IDLE",
        position={"side": "flat", "size": 0},
        risk={"breach": False},
        last_decision={},
    )


def make_context():
    return ExecutionContext(
        authority="live-trade",
        position={"side": "flat", "size": 0},
        risk={"breach": False},
        health="normal",
        kill_switch=False,
    )


def test_one_intent_one_step():
    engine = TimelineEngine(
        orchestrator=ExecutionOrchestrator(),
        initial_state=make_state(),
        context=make_context(),
    )

    event = engine.step(make_intent())

    assert event.index == 1
    assert engine.timeline_index() == 1
