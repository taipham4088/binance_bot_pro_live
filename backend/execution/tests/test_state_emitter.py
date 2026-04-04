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
from backend.execution.emission.state_emitter import StateEmitter
from backend.execution.types.execution_state import ExecutionState


def make_state(
    execution_state="IDLE",
    timeline_index=0,
    last_decision=None,
):
    return ExecutionState(
        meta={
            "session_id": "s1",
            "mode": "live",
            "timeline_index": timeline_index,
            "timestamp": 0,
        },
        authority="live-trade",
        health="normal",
        execution_state=execution_state,
        position={"side": "flat", "size": 0},
        risk={"breach": False, "kill_switch": False},
        last_decision=last_decision or {},
    )


# --------------------------------------------------
# SNAPSHOT RULES
# --------------------------------------------------

def test_first_emit_is_snapshot():
    emitter = StateEmitter()
    state = make_state()

    msg = emitter.emit(state)

    assert msg["type"] == "SNAPSHOT"
    assert "payload" in msg
    assert msg["payload"]["execution_state"] == "IDLE"


# --------------------------------------------------
# DELTA RULES
# --------------------------------------------------

def test_second_emit_is_delta():
    emitter = StateEmitter()

    state1 = make_state()
    state2 = make_state(
        execution_state="OPENING",
        timeline_index=1,
        last_decision={
            "plan": "OPEN_POSITION",
            "reason": "flat -> open_long",
            "source": "manual",
            "timestamp": 1,
        },
    )

    emitter.emit(state1)
    msg = emitter.emit(state2)

    assert msg["type"] == "DELTA"
    assert isinstance(msg["payload"], list)
    assert len(msg["payload"]) > 0


def test_delta_contains_execution_state_change():
    emitter = StateEmitter()

    state1 = make_state(execution_state="IDLE")
    state2 = make_state(execution_state="OPENING", timeline_index=1)

    emitter.emit(state1)
    msg = emitter.emit(state2)

    paths = [p["path"] for p in msg["payload"]]
    assert "/execution_state" in paths


def test_delta_contains_last_decision_change():
    emitter = StateEmitter()

    state1 = make_state()
    state2 = make_state(
        timeline_index=1,
        last_decision={
            "plan": "OPEN_POSITION",
            "reason": "test",
            "source": "manual",
            "timestamp": 1,
        },
    )

    emitter.emit(state1)
    msg = emitter.emit(state2)

    paths = [p["path"] for p in msg["payload"]]
    assert "/last_decision" in paths


# --------------------------------------------------
# SNAPSHOT / DELTA INVARIANT
# --------------------------------------------------

def test_snapshot_then_delta_order():
    emitter = StateEmitter()

    s1 = make_state()
    s2 = make_state(execution_state="OPENING", timeline_index=1)
    s3 = make_state(execution_state="OPEN", timeline_index=2)

    msg1 = emitter.emit(s1)
    msg2 = emitter.emit(s2)
    msg3 = emitter.emit(s3)

    assert msg1["type"] == "SNAPSHOT"
    assert msg2["type"] == "DELTA"
    assert msg3["type"] == "DELTA"
