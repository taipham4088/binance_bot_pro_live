import time
from typing import Dict, Optional

from backend.core.exchange.exchange_adapter import (
    ExchangeAdapter,
    ExchangeOrder,
    ExchangePosition,
)


# =========================
# Live Exchange Adapter
# =========================

class LiveExchangeAdapter(ExchangeAdapter):
    """
    STEP 13.2 – Live Exchange Adapter (SAFE STUB)

    Default behavior:
    - live_trade_enabled = False
    - Any order attempt → REJECTED

    This prevents accidental real trading.
    """

    def __init__(
        self,
        exchange_name: str,
        api_key: str,
        api_secret: str,
        live_trade_enabled: bool = False,
    ):
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.live_trade_enabled = live_trade_enabled

        # In-memory mirrors (for snapshot / debug)
        self._orders: Dict[str, ExchangeOrder] = {}
        self._positions: Dict[str, ExchangePosition] = {}
        self._order_seq: int = 0

    # -------------------------
    # Guards
    # -------------------------

    def _ensure_live_enabled(self) -> None:
        if not self.live_trade_enabled:
            raise RuntimeError(
                "Live trading is DISABLED. "
                "Set live_trade_enabled=True explicitly to allow execution."
            )

    # -------------------------
    # ExchangeAdapter API
    # -------------------------

    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
    ) -> ExchangeOrder:
        """
        Market order (LIVE).
        """
        self._ensure_live_enabled()

        self._order_seq += 1
        order_id = f"LIVE-{self._order_seq}"

        # NOTE:
        # Real implementation will call exchange SDK / REST here.
        order = ExchangeOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=None,
            status="NEW",
        )

        self._orders[order_id] = order

        # ---- PLACEHOLDER ----
        # Real fill handling will be async via WS.
        order.status = "FILLED"
        order.filled_qty = qty

        # Position mirror update (simplified)
        delta = qty if side == "buy" else -qty
        pos = self._positions.get(symbol)
        if not pos:
            self._positions[symbol] = ExchangePosition(
                symbol=symbol,
                size=delta,
                avg_price=0.0,
            )
        else:
            pos.size += delta
            if pos.size == 0:
                del self._positions[symbol]

        return order

    def cancel_order(self, order_id: str) -> None:
        self._ensure_live_enabled()

        order = self._orders.get(order_id)
        if not order:
            return
        if order.status != "NEW":
            return

        # Real implementation will call exchange cancel endpoint
        order.status = "CANCELED"

    def get_position(self, symbol: str) -> Optional[ExchangePosition]:
        return self._positions.get(symbol)

    def close_position(self, symbol: str) -> None:
        self._ensure_live_enabled()

        pos = self._positions.get(symbol)
        if not pos:
            return

        side = "sell" if pos.size > 0 else "buy"
        self.place_market_order(
            symbol=symbol,
            side=side,
            qty=abs(pos.size),
        )

    def snapshot(self) -> Dict:
        return {
            "exchange": self.exchange_name,
            "live_trade_enabled": self.live_trade_enabled,
            "positions": {
                s: {
                    "size": p.size,
                    "avg_price": p.avg_price,
                }
                for s, p in self._positions.items()
            },
            "orders": {
                oid: {
                    "symbol": o.symbol,
                    "side": o.side,
                    "qty": o.qty,
                    "status": o.status,
                }
                for oid, o in self._orders.items()
            },
        }
