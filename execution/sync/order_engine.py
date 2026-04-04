from .models import OrderState
import time


class OrderEngine:

    def __init__(self):
        self.orders = {}

    def apply_snapshot(self, orders):
        self.orders.clear()
        for o in orders:
            self.orders[o.order_id] = OrderState(
                order_id=o.order_id,
                client_id=o.client_id,
                symbol=o.symbol,
                side=o.side,
                status=o.status,
                price=o.price,
                qty=o.qty,
                filled=o.filled,
                last_update=time.time()
            )

        return list(self.orders.values())

    def apply_event(self, o):
        self.orders[o.order_id] = OrderState(
            order_id=o.order_id,
            client_id=o.client_id,
            symbol=o.symbol,
            side=o.side,
            status=o.status,
            price=o.price,
            qty=o.qty,
            filled=o.filled,
            last_update=time.time()
        )

        return self.orders[o.order_id]
    # ===== STEP 4 VIEW =====
    def get_open_orders(self):
        return list(self.orders.values())

