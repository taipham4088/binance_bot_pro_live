from backend.execution.adapter.live_adapter_base import LiveAdapterBase
from backend.execution.types.execution_state import ExecutionState


class BinanceFuturesReadOnlyAdapter(LiveAdapterBase):
    """
    Stage 3.0 – Binance Futures READ ONLY
    """

    def __init__(self, client, symbol: str):
        super().__init__(dry_run=True)
        self._client = client
        self._symbol = symbol

    # -----------------------------
    # SYNC
    # -----------------------------
    def sync_account(self):
        return self._client.get_account()

    def sync_position(self):
        positions = self._client.get_positions()
        for p in positions:
            if p["symbol"] == self._symbol:
                return {
                    "side": p["side"],
                    "size": p["size"],
                    "entry_price": p["entry_price"],
                }

        return {
            "side": "flat",
            "size": 0,
            "entry_price": 0,
        }

    # -----------------------------
    # EXECUTION (BLOCKED)
    # -----------------------------
    def execute(self, plan, state: ExecutionState) -> ExecutionState:
        # READ ONLY – tuyệt đối không gửi lệnh
        return state

    def cancel_all_orders(self):
        # READ ONLY
        return None
