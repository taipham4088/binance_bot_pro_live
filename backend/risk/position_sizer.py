from dataclasses import dataclass
from backend.runtime.runtime_config import runtime_config
from backend.exchange.binance_filters import BinanceFilters
from backend.exchange.exchange_info_cache import ExchangeInfoCache

@dataclass
class PositionSizeResult:
    """
    Result of position sizing calculation.
    """

    qty: float
    risk_amount: float
    stop_distance: float
    capped: bool


class PositionSizer:
    """
    Calculates position size based on risk per trade and stop loss distance.

    Formula:
        size = (equity * risk_percent) / stop_distance
    """

    def __init__(
        self,
        risk_per_trade: float = 0.01,
        max_position_size: float = 0.05,
        min_stop_distance: float = 1e-6,
    ):
        """
        Parameters
        ----------
        risk_per_trade : float
            Fraction of equity risked per trade (e.g. 0.01 = 1%)

        max_position_size : float
            Hard cap for position size

        min_stop_distance : float
            Guard against division by zero / extremely tight SL
        """
        self.exchange_info = ExchangeInfoCache()
        self.filters = BinanceFilters(self.exchange_info)

        self.risk_per_trade = risk_per_trade
        self.max_position_size = max_position_size
        self.min_stop_distance = min_stop_distance

    # ==========================================================
    # MAIN CALCULATION
    # ==========================================================

    def calculate(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
    ) -> PositionSizeResult:

        stop_distance = abs(entry_price - stop_loss)

        if stop_distance < self.min_stop_distance:
            raise ValueError("Stop distance too small")

        risk_percent = runtime_config.get("risk_percent", self.risk_per_trade)

        risk_amount = equity * risk_percent

        qty = risk_amount / stop_distance
        qty = self.filters.round_quantity(
            symbol="BTCUSDT", 
            quantity=qty
        )
        if not self.filters.check_min_notional(
            symbol="BTCUSDT",
            quantity=qty,
            price=entry_price
        ):
            raise ValueError("Position size below exchange minimum")

        capped = False

        if qty > self.max_position_size:
            qty = self.max_position_size
            capped = True

        return PositionSizeResult(
            qty=qty,
            risk_amount=risk_amount,
            stop_distance=stop_distance,
            capped=capped,
        )

    # ==========================================================
    # CONFIG UPDATE
    # ==========================================================

    def update_config(
        self,
        risk_per_trade: float | None = None,
        max_position_size: float | None = None,
    ):

        if risk_per_trade is not None:
            self.risk_per_trade = risk_per_trade

        if max_position_size is not None:
            self.max_position_size = max_position_size

    # ==========================================================
    # DEBUG LOG
    # ==========================================================

    def debug_print(self, result: PositionSizeResult):

        print("[POSITION SIZER]")
        print(" risk_amount =", result.risk_amount)
        print(" stop_distance =", result.stop_distance)
        print(" qty =", result.qty)
        print(" capped =", result.capped)