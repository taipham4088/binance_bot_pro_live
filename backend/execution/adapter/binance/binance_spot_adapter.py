from backend.execution.adapter.live_adapter_base import LiveAdapterBase
from backend.execution.types.execution_state import ExecutionState


class BinanceSpotAdapter(LiveAdapterBase):
    """
    Binance Spot Adapter
    Stage 3.x – mặc định READ-ONLY
    """

    def __init__(self, client, symbol: str):
        super().__init__(dry_run=True)
        self._client = client
        self._symbol = symbol

    # -----------------------------
    # READ ONLY SYNC
    # -----------------------------

    def sync_account(self):
        return self._client.get_account()

    def sync_position(self):
        raw = self._client.get_position()
        if not raw:
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

    # -----------------------------
    # EXECUTION (BLOCKED / READ-ONLY)
    # -----------------------------

    def execute(self, plan, state: ExecutionState) -> ExecutionState:
        # Spot READ-ONLY: không gửi lệnh
        return state

    def cancel_all_orders(self):
        return None
