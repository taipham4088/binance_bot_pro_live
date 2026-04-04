from abc import ABC, abstractmethod
from backend.execution.types.execution_plan import ExecutionPlan
from backend.execution.types.execution_state import ExecutionState


class BaseExecutionAdapter(ABC):
    """
    Adapter = tay chân
    - Không quyết định
    - Không bypass Decision Table
    """

    @abstractmethod
    def execute(self, plan: ExecutionPlan, state: ExecutionState) -> ExecutionState:
        """
        Apply execution effect to state (paper or live)
        Must return UPDATED state
        """
        raise NotImplementedError
