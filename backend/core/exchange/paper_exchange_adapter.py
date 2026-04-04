import time
from dataclasses import dataclass
from typing import Dict, Optional, List


# =========================
# Paper Exchange Models
# =========================

@dataclass
class PaperOrder:
    order_id: str
    symbol: str
    side: str          # buy | sell
    qty: float
    price: float
    status: str        # OPEN | FILLED | CANCELED
    created_at: float
    filled_at: Optional[float] = None


@dataclass
class PaperPosition:
    symbol: str
    size: float = 0.0
    avg_price: float = 0.0


# =========================
# Paper Exchange Adapter
# =========================

class PaperExchangeAdapter:
    """
    STEP 13.1 – Paper Exchange Adapter

    Responsibilities:
    - Simulate order placement & fill
    - Maintain in-memory orders & positions
    - Emit deterministic fills (market-like)
    - NO networking
    - NO real exchange
    """

    def __init__(self, initial_price_feed: Optional[Dict[str, float]] = None):
        """
        initial_price_feed: symbol -> price
        """
        self.prices: Dict[str, float] = initial_price_feed or {}
        self.orders: Dict[str, PaperOrder] = {}
        self.positions: Dict[str, PaperPosition] = {}
        self._order_seq: int = 0

    # -------------------------
    # Price Feed (Stub)
    # -------------------------

    def update_price(self, symbol: str, price: float) -> None:
        self.prices[symbol] = price

    def get_price(self, symbol: str) -> float:
        price = self.prices.get(symbol)
        if price is None:
            raise RuntimeError(f"No price for symbol {symbol}")
        return price

    # -------------------------
    # Order API
    # -------------------------

    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
    ) -> PaperOrder:
        """
        Market order: fill immediately at current price.
        """
        price = self.get_price(symbol)

        self._order_seq += 1
        order_id = f"PAPER-{self._order_seq}"

        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            status="OPEN",
            created_at=time.time(),
        )

        self.orders[order_id] = order

        # Immediate fill
        self._fill_order(order)

        return order

    def cancel_order(self, order_id: str) -> None:
        order = self.orders.get(order_id)
        if not order:
            return
        if order.status != "OPEN":
            return

        order.status = "CANCELED"

    # -------------------------
    # Fill Logic
    # -------------------------

    def _fill_order(self, order: PaperOrder) -> None:
        """
        Deterministic fill (no slippage by default).
        """
        order.status = "FILLED"
        order.filled_at = time.time()

        qty = order.qty if order.side == "buy" else -order.qty
        self._apply_fill(order.symbol, qty, order.price)

    def _apply_fill(self, symbol: str, qty: float, price: float) -> None:
        pos = self.positions.get(symbol)

        if not pos:
            self.positions[symbol] = PaperPosition(
                symbol=symbol,
                size=qty,
                avg_price=price,
            )
            return

        # Position update
        new_size = pos.size + qty

        # Fully closed
        if new_size == 0:
            del self.positions[symbol]
            return

        # Same direction → update avg price
        if pos.size * qty > 0:
            total_cost = (pos.avg_price * abs(pos.size)) + (price * abs(qty))
            pos.size = new_size
            pos.avg_price = total_cost / abs(new_size)
            return

        # Reduce / flip
        pos.size = new_size
        pos.avg_price = price

    # -------------------------
    # Observer / Debug
    # -------------------------

    def snapshot(self) -> dict:
        return {
            "prices": dict(self.prices),
            "positions": {
                s: {
                    "size": p.size,
                    "avg_price": p.avg_price,
                }
                for s, p in self.positions.items()
            },
            "orders": {
                oid: {
                    "symbol": o.symbol,
                    "side": o.side,
                    "qty": o.qty,
                    "price": o.price,
                    "status": o.status,
                }
                for oid, o in self.orders.items()
            },
        }
