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
from backend.execution.state_machine.execution_states import ExecutionStates
from backend.execution.decision.decision_types import ExecutionPlanType


def transition_state(current_state: str, execution_plan: ExecutionPlanType) -> str:
    """
    STATE MACHINE – PURE TRANSITION GRAPH
    """

    # --------------------------------------------------
    # GLOBAL BLOCK
    # --------------------------------------------------
    if execution_plan == ExecutionPlanType.BLOCK:
        return ExecutionStates.BLOCKED

    # --------------------------------------------------
    # IDLE
    # --------------------------------------------------
    if current_state == ExecutionStates.IDLE:
        if execution_plan == ExecutionPlanType.OPEN_POSITION:
            return ExecutionStates.OPENING
        return ExecutionStates.IDLE

    # --------------------------------------------------
    # OPEN
    # --------------------------------------------------
    if current_state == ExecutionStates.OPEN:
        if execution_plan == ExecutionPlanType.REDUCE_ONLY:
            return ExecutionStates.REDUCING
        if execution_plan == ExecutionPlanType.CLOSE_POSITION:
            return ExecutionStates.CLOSING
        return ExecutionStates.OPEN

    # --------------------------------------------------
    # OPENING
    # --------------------------------------------------
    if current_state == ExecutionStates.OPENING:
        return ExecutionStates.OPENING

    # --------------------------------------------------
    # REDUCING
    # --------------------------------------------------
    if current_state == ExecutionStates.REDUCING:
        return ExecutionStates.OPEN

    # --------------------------------------------------
    # CLOSING
    # --------------------------------------------------
    if current_state == ExecutionStates.CLOSING:
        return ExecutionStates.IDLE

    # --------------------------------------------------
    # BLOCKED
    # --------------------------------------------------
    if current_state == ExecutionStates.BLOCKED:
        return ExecutionStates.BLOCKED

    # --------------------------------------------------
    # ERROR
    # --------------------------------------------------
    if current_state == ExecutionStates.ERROR:
        return ExecutionStates.ERROR

    # --------------------------------------------------
    # FALLBACK
    # --------------------------------------------------
    return ExecutionStates.ERROR
