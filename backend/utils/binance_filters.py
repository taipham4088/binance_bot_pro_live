import math


class BinanceFilters:
    """
    Utility for applying Binance Futures trading filters.

    Handles:
    - tick size (price rounding)
    - step size (quantity rounding)
    - min notional guard
    """

    def __init__(
        self,
        tick_size: float,
        step_size: float,
        min_notional: float | None = None
    ):
        self.tick_size = tick_size
        self.step_size = step_size
        self.min_notional = min_notional

    # ==========================================================
    # PRICE ROUNDING
    # ==========================================================

    def round_price(self, price: float) -> float:
        """
        Round price to Binance tick size.
        """

        return math.floor(price / self.tick_size) * self.tick_size

    # ==========================================================
    # QUANTITY ROUNDING
    # ==========================================================

    def round_qty(self, qty: float) -> float:
        """
        Round quantity to Binance step size.
        """

        return math.floor(qty / self.step_size) * self.step_size

    # ==========================================================
    # NOTIONAL CHECK
    # ==========================================================

    def validate_notional(self, price: float, qty: float):

        if self.min_notional is None:
            return True

        notional = price * qty

        if notional < self.min_notional:
            raise ValueError(
                f"Order notional too small: {notional} < {self.min_notional}"
            )

        return True

    # ==========================================================
    # FULL ORDER SANITIZE
    # ==========================================================

    def sanitize_order(self, price: float, qty: float):

        price = self.round_price(price)
        qty = self.round_qty(qty)

        if qty <= 0:
            raise ValueError("Quantity too small after rounding")

        if self.min_notional:
            self.validate_notional(price, qty)

        return price, qty