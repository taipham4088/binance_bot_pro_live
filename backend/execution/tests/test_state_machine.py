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
from backend.execution.state_machine.state_transition import transition_state
from backend.execution.state_machine.execution_states import ExecutionStates
from backend.execution.decision.decision_types import ExecutionPlanType


def test_block_always_goes_to_blocked():
    next_state = transition_state(
        ExecutionStates.OPEN,
        ExecutionPlanType.BLOCK,
    )
    assert next_state == ExecutionStates.BLOCKED


def test_blocked_does_not_auto_resume():
    next_state = transition_state(
        ExecutionStates.BLOCKED,
        ExecutionPlanType.NOOP,
    )
    assert next_state == ExecutionStates.BLOCKED


def test_open_cannot_open_again():
    next_state = transition_state(
        ExecutionStates.OPEN,
        ExecutionPlanType.OPEN_POSITION,
    )
    assert next_state == ExecutionStates.OPEN


def test_closing_goes_to_idle():
    next_state = transition_state(
        ExecutionStates.CLOSING,
        ExecutionPlanType.NOOP,
    )
    assert next_state == ExecutionStates.IDLE
