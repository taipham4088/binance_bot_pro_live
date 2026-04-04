from backend.execution.adapter.live_adapter_base import LiveAdapterBase
from backend.execution.types.execution_state import ExecutionState


class LiveReadOnlyAdapter(LiveAdapterBase):
    """
    Stage 3.0 – READ ONLY
    - Sync account / position
    - NO execution
    """

    def __init__(self, exchange_client):
        super().__init__(dry_run=True)
        self._client = exchange_client

    # --------------------------------------------------
    # READ ONLY SYNC
    # --------------------------------------------------

    def sync_account(self):
        """
        Exchange-specific call
        Must return normalized dict
        """
        raw = self._client.get_account()
        return {
            "balance": raw["balance"],
            "available": raw["available"],
            "unrealized_pnl": raw.get("unrealized_pnl", 0),
        }

    def sync_position(self):
        """
        Return normalized position
        """
        raw = self._client.get_position()
        if raw is None:
            return {
                "side": "flat",
                "size": 0,
                "entry_price": 0,
            }

        return {
            "side": raw["side"],
            "size": raw["size"],
            "entry_price": raw["entry_price"],
        }

    # --------------------------------------------------
    # EXECUTION (BLOCKED)
    # --------------------------------------------------

    def execute(self, plan, state: ExecutionState) -> ExecutionState:
        """
        READ ONLY → MUST NOT EXECUTE
        """
        return state

    def cancel_all_orders(self):
        """
        READ ONLY → DO NOTHING
        """
        return None
