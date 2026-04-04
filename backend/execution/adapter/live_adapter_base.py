from abc import ABC, abstractmethod
from typing import Dict, Any

from backend.execution.types.execution_plan import ExecutionPlan
from backend.execution.types.execution_state import ExecutionState


class LiveAdapterBase(ABC):
    """
    LIVE ADAPTER CONTRACT

    Adapter = tay chân
    - Không decision
    - Không tự reverse
    - Không net mù
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    # --------------------------------------------------
    # ACCOUNT / HEALTH (READ-ONLY)
    # --------------------------------------------------

    @abstractmethod
    def sync_account(self) -> Dict[str, Any]:
        """
        Return normalized account info:
        {
          balance,
          margin,
          available,
          unrealized_pnl
        }
        """
        raise NotImplementedError

    @abstractmethod
    def sync_position(self) -> Dict[str, Any]:
        """
        Return normalized position:
        {
          side: long | short | flat,
          size: number,
          entry_price: number
        }
        """
        raise NotImplementedError

    # --------------------------------------------------
    # EXECUTION (ONLY WHEN ALLOWED)
    # --------------------------------------------------

    @abstractmethod
    def execute(self, plan: ExecutionPlan, state: ExecutionState) -> ExecutionState:
        """
        Execute EXACTLY the plan given by Orchestrator

        Rules:
        - BLOCK  -> do nothing
        - NOOP   -> do nothing
        - OPEN   -> open position (correct side)
        - REDUCE -> reduce-only
        - CLOSE  -> close position

        dry_run=True:
        - DO NOT send order
        - LOG intent instead
        """
        raise NotImplementedError

    # --------------------------------------------------
    # SAFETY
    # --------------------------------------------------

    @abstractmethod
    def cancel_all_orders(self):
        """
        Emergency cancel
        """
        raise NotImplementedError
