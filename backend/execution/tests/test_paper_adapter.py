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
from backend.execution.adapter.paper_adapter import PaperExecutionAdapter
from backend.execution.types.execution_state import ExecutionState
from backend.execution.types.execution_plan import ExecutionPlan
from backend.execution.decision.decision_types import ExecutionPlanType


def make_state():
    return ExecutionState(
        meta={},
        authority="paper",
        health="normal",
        execution_state="IDLE",
        position={"side": "flat", "size": 0},
        risk={},
        last_decision={},
    )


def test_open_position_paper():
    adapter = PaperExecutionAdapter()
    plan = ExecutionPlan(
        plan=ExecutionPlanType.OPEN_POSITION,
        reason="flat -> open_long",
        source="manual",
        timestamp=0,
    )

    state = adapter.execute(plan, make_state())
    assert state.position["side"] == "long"
    assert state.execution_state == "OPEN"
