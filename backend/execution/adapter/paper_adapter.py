from copy import deepcopy

from backend.execution.adapter.base_adapter import BaseExecutionAdapter
from backend.execution.decision.decision_types import ExecutionPlanType
from backend.execution.state_machine.execution_states import ExecutionStates
from backend.execution.types.execution_state import ExecutionState


class PaperExecutionAdapter(BaseExecutionAdapter):
    """
    Paper adapter:
    - No real orders
    - Deterministic
    - Immediate fill
    """

    def execute(self, plan, state: ExecutionState) -> ExecutionState:
        new_state = deepcopy(state)

        # Respect BLOCK
        if plan.plan == ExecutionPlanType.BLOCK:
            new_state.execution_state = ExecutionStates.BLOCKED
            return new_state

        # OPEN
        if plan.plan == ExecutionPlanType.OPEN_POSITION:
            new_state.execution_state = ExecutionStates.OPEN
            new_state.position = {
                "side": "long" if "long" in plan.reason else "short",
                "size": 1,
                "entry_price": 0,
            }
            return new_state

        # REDUCE
        if plan.plan == ExecutionPlanType.REDUCE_ONLY:
            new_state.execution_state = ExecutionStates.OPEN
            new_state.position["size"] = max(0, new_state.position.get("size", 0) - 1)
            if new_state.position["size"] == 0:
                new_state.position["side"] = "flat"
                new_state.execution_state = ExecutionStates.IDLE
            return new_state

        # CLOSE
        if plan.plan == ExecutionPlanType.CLOSE_POSITION:
            new_state.execution_state = ExecutionStates.IDLE
            new_state.position = {
                "side": "flat",
                "size": 0,
                "entry_price": 0,
            }
            return new_state

        # NOOP
        return new_state
