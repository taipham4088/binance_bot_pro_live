from typing import Optional


class PositionSyncService:
    """
    Synchronize exchange positions into SystemStateEngine at startup.

    This prevents local/exchange position mismatch after restart.
    """

    def __init__(self, exchange_adapter, system_state_engine, symbol: str):
        self.exchange = exchange_adapter
        self.state_engine = system_state_engine
        self.symbol = symbol

    # --------------------------------------------------

    def sync(self):

        print("[POSITION SYNC] Starting exchange position sync...")

        positions = self.exchange.get_positions()

        if not positions:
            print("[POSITION SYNC] No open positions on exchange.")
            return

        for p in positions:

            if p.symbol != self.symbol:
                continue

            side = p.side
            size = p.size

            print(
                f"[POSITION SYNC] Found exchange position "
                f"{side} {size} {p.symbol}"
            )

            self._apply_position(side, size)

        print("[POSITION SYNC] Completed.")

    # --------------------------------------------------

    def _apply_position(self, side: str, size: float):

        execution_state = self.state_engine.get_block("execution")

        execution_state["positions"][self.symbol] = {
            "side": side,
            "size": size,
        }

        self.state_engine.update_block("execution", execution_state)

        print(
            f"[POSITION SYNC] Local execution state updated → "
            f"{side} {size}"
        )