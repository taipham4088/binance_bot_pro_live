# execution/exchange_guard.py

from decimal import Decimal, ROUND_DOWN


class ExchangeValidationError(Exception):
    pass


class ExchangeGuard:
    """
    Exchange hardening layer.
    Does NOT know intent logic.
    Does NOT calculate size.
    Only validates order before sending to exchange.
    """

    def __init__(self, exchange_info: dict):
        """
        exchange_info must contain:
            min_notional
            min_qty
            max_qty
            step_size
            price_precision
            qty_precision
        """
        self.min_notional = Decimal(str(exchange_info["min_notional"]))
        self.min_qty = Decimal(str(exchange_info["min_qty"]))
        self.max_qty = Decimal(str(exchange_info["max_qty"]))
        self.step_size = Decimal(str(exchange_info["step_size"]))
        self.price_precision = int(exchange_info["price_precision"])
        self.qty_precision = int(exchange_info["qty_precision"])

    # -----------------------------------------------------
    # PUBLIC ENTRY
    # -----------------------------------------------------

    def validate_and_sanitize(self, price: float, quantity: float):
        """
        Returns sanitized_quantity (Decimal)
        Raises ExchangeValidationError if invalid
        """

        price = Decimal(str(price))
        quantity = Decimal(str(quantity))

        quantity = self._apply_step_rounding(quantity)
        self._validate_qty_bounds(quantity)
        self._validate_notional(price, quantity)

        return quantity

    # -----------------------------------------------------
    # INTERNAL VALIDATIONS
    # -----------------------------------------------------

    def _apply_step_rounding(self, quantity: Decimal) -> Decimal:
        """
        Round DOWN to nearest step size.
        Exchange requires flooring.
        """
        steps = (quantity / self.step_size).to_integral_value(rounding=ROUND_DOWN)
        rounded = steps * self.step_size
        return rounded.quantize(
            Decimal(10) ** -self.qty_precision,
            rounding=ROUND_DOWN,
        )

    def _validate_qty_bounds(self, quantity: Decimal):
        if quantity < self.min_qty:
            raise ExchangeValidationError(
                f"Quantity below min_qty: {quantity} < {self.min_qty}"
            )
        if quantity > self.max_qty:
            raise ExchangeValidationError(
                f"Quantity above max_qty: {quantity} > {self.max_qty}"
            )

    def _validate_notional(self, price: Decimal, quantity: Decimal):
        notional = price * quantity
        if notional < self.min_notional:
            raise ExchangeValidationError(
                f"Notional too small: {notional} < {self.min_notional}"
            )
