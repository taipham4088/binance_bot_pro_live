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
from backend.execution.divergence.divergence_detector import DivergenceDetector
from backend.execution.divergence.divergence_types import DivergenceType


def test_no_divergence():
    d = DivergenceDetector()

    live_event = {"index": 1, "decision": {"plan": "OPEN"}}
    replay_event = {"index": 1, "decision": {"plan": "OPEN"}}

    live_state = {"execution_state": "OPEN", "position": {}, "last_decision": {}}
    replay_state = {"execution_state": "OPEN", "position": {}, "last_decision": {}}

    r = d.compare_step(1, live_event, replay_event, live_state, replay_state)
    assert r["type"] == DivergenceType.NONE


def test_decision_divergence():
    d = DivergenceDetector()

    live_event = {"index": 1, "decision": {"plan": "OPEN"}}
    replay_event = {"index": 1, "decision": {"plan": "CLOSE"}}

    r = d.compare_step(1, live_event, replay_event, {}, {})
    assert r["type"] == DivergenceType.DECISION


def test_state_divergence():
    d = DivergenceDetector()

    live_event = {"index": 1, "decision": {}}
    replay_event = {"index": 1, "decision": {}}

    live_state = {"execution_state": "OPEN"}
    replay_state = {"execution_state": "IDLE"}

    r = d.compare_step(1, live_event, replay_event, live_state, replay_state)
    assert r["type"] == DivergenceType.STATE


def test_order_divergence():
    d = DivergenceDetector()

    live_event = {"index": 2}
    replay_event = {"index": 1}

    r = d.compare_step(1, live_event, replay_event, {}, {})
    assert r["type"] == DivergenceType.ORDER
