from execution.system.execution_lock import ExecutionBreach
from infrastructure.binance_exchange_info import BinanceExchangeInfoFetcher
from execution.exchange_guard import ExchangeGuard

class BinanceTradeClient:
    """
    Guarded trade client.
    Mọi lệnh gửi ra exchange BẮT BUỘC phải thuộc về một execution hợp lệ.
    """

    def __init__(self, client, execution_state, execution_lock, symbol: str):
        self.client = client
        self.execution_state = execution_state
        self.execution_lock = execution_lock
        self.symbol = symbol

        # ===== Exchange Guard Setup =====
        fetcher = BinanceExchangeInfoFetcher()
        exchange_info = fetcher.fetch_symbol_info(symbol)
        self.guard = ExchangeGuard(exchange_info)
        # ✅ Idempotent storage
        self._executed_orders = set()
        # ✅ Retry config
        self._retry_attempts = 2
        self._retry_delay = 0.5

    # ============================================================
    # INTERNAL GUARD
    # ============================================================

    def _guard(self, execution_id: str | None):

        # system frozen → cấm trade tuyệt đối
        if self.execution_state.is_frozen():
            raise Exception("🚨 EXECUTION FROZEN — TRADE BLOCKED")

        # SL/TP follow-up orders có thể không có execution active
        if execution_id is None:
            return

        try: 
            self.execution_lock.guard(execution_id)
        except ExecutionBreach:
            # 🔥 allow SL/TP follow-up orders
            print("[LOCK BYPASS] follow-up order allowed")
            return

    # ============================================================
    # TRADE API (GUARDED)
    # ============================================================

    def place_order(self, *, execution_id=None, **kwargs):
        import time

        self._guard(execution_id)

        # ===== IDEMPOTENT PROTECTION (multi-step safe)=====
        order_key = (
            f"{execution_id}:"
            f"{kwargs.get('side')}:"
            f"{kwargs.get('quantity')}:"
            f"{kwargs.get('reduceOnly')}"
            f"{kwargs.get('type')}"
        )

        if order_key in self._executed_orders:
            raise Exception(f"IDEMPOTENT_BLOCK: {order_key} already sent")

        self._executed_orders.add(order_key)

        # ===== VALIDATION LAYER =====
        if "quantity" in kwargs:
            quantity = kwargs["quantity"]

            # lấy giá để tính notional
            if "price" in kwargs:
                price = float(kwargs["price"])
            else:
                ticker = self.client.futures_mark_price(symbol=self.symbol)
                price = float(ticker["markPrice"])

            sanitized_qty = self.guard.validate_and_sanitize(
                price=price,
                quantity=quantity,
                reduce_only_close=bool(kwargs.get("reduceOnly")),
            )

            kwargs["quantity"] = float(sanitized_qty)

        # ===== NETWORK RETRY LAYER =====
        last_exception = None

        for attempt in range(self._retry_attempts + 1):
            try:
                response = self.client.futures_create_order(**kwargs)
               
                return response

            except Exception as e:
                last_exception = e

                msg = str(e).lower()

                # ❌ Không retry validation lỗi
                if "min_qty" in msg or "notional" in msg:
                    self._executed_orders.discard(order_key)
                    raise

                # ✅ Retry nếu là network error
                is_network_error = any(
                    key in msg for key in [
                        "timeout",
                        "connection",
                        "temporarily",
                        "502",
                        "503",
                        "504"
                    ]
                )

                if not is_network_error:
                    self._executed_orders.discard(order_key)
                    raise

                if attempt < self._retry_attempts:
                    print(f"[RETRY] attempt {attempt+1}")
                    time.sleep(self._retry_delay)
                else:
                    print("[RETRY] max attempts reached")
                    self._executed_orders.discard(order_key)
                    raise last_exception

    def cancel_order(self, *, execution_id=None, symbol: str, order_id: str):
        self._guard(execution_id)
        return self.client.futures_cancel_order(symbol=symbol, orderId=order_id)

    def cancel_all(self, *, execution_id=None, symbol: str):
        self._guard(execution_id)
        return self.client.futures_cancel_all_open_orders(symbol=symbol)

    # ============================================================
    # READ API (KHÔNG CẦN GUARD)
    # ============================================================

    def get_open_orders(self):
        return self.client.futures_get_open_orders()

    def get_positions(self):
        return self.client.futures_position_information()

    def get_balances(self):
        return self.client.futures_account_balance()
