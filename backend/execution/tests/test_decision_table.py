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
from backend.execution.decision.decision_table import evaluate_decision
from backend.execution.decision.decision_types import Authority, HealthState, ExecutionPlanType
from backend.execution.types.intent import Intent


def make_intent(intent_type: str):
    return Intent(
        intent_id="i1",
        session_id="s1",
        source="manual",
        type=intent_type,
        payload={},
        timestamp=0,
    )


def base_context(**overrides):
    ctx = {
        "authority": Authority.LIVE_TRADE,
        "position": {"side": "flat", "size": 0},
        "intent": make_intent("open_long"),
        "risk": {"breach": False},
        "health": HealthState.NORMAL,
        "kill_switch": False,
    }
    ctx.update(overrides)
    return ctx


def test_live_readonly_is_always_blocked():
    plan = evaluate_decision(
        base_context(authority=Authority.LIVE_READONLY)
    )
    assert plan.plan == ExecutionPlanType.BLOCK


def test_kill_switch_blocks_everything():
    plan = evaluate_decision(
        base_context(kill_switch=True)
    )
    assert plan.plan == ExecutionPlanType.BLOCK


def test_health_degraded_blocks_open():
    plan = evaluate_decision(
        base_context(
            health=HealthState.DEGRADED,
            intent=make_intent("open_long"),
        )
    )
    assert plan.plan == ExecutionPlanType.BLOCK


def test_long_open_short_requires_close_first():
    plan = evaluate_decision(
        base_context(
            position={"side": "long", "size": 1},
            intent=make_intent("open_short"),
        )
    )
    assert plan.plan == ExecutionPlanType.CLOSE_POSITION
