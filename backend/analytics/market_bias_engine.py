# backend/analytics/market_bias_engine.py

from typing import Dict, Optional


class MarketBiasEngine:
    """
    Market Bias Engine

    Computes:
    - Strategy Bias
    - Execution Bias
    - Market Bias (Combined)

    Safe:
    - No execution modification
    - Analytics layer only
    """

    def __init__(self):
        self.strategy_bias: str = "NEUTRAL"
        self.execution_bias: str = "NEUTRAL"
        self.market_bias: str = "NEUTRAL"

    # ------------------------------
    # Strategy Bias
    # ------------------------------

    def update_strategy_bias(self, side: Optional[str]):

        if side is None:
            self.strategy_bias = "NEUTRAL"
            return

        side = side.upper()

        if side == "LONG":
            self.strategy_bias = "BULLISH"
        elif side == "SHORT":
            self.strategy_bias = "BEARISH"
        else:
            self.strategy_bias = "NEUTRAL"

    # ------------------------------
    # Execution Bias
    # ------------------------------

    def update_execution_bias(self, position: Dict):

        if not position:
            self.execution_bias = "NEUTRAL"
            return

        side = position.get("side")

        if not side:
            self.execution_bias = "NEUTRAL"
            return

        side = side.upper()

        if side == "LONG":
            self.execution_bias = "BULLISH"
        elif side == "SHORT":
            self.execution_bias = "BEARISH"
        else:
            self.execution_bias = "NEUTRAL"

    # ------------------------------
    # Market Bias Combine
    # ------------------------------

    def compute_market_bias(self):

        if self.strategy_bias == "BULLISH" and self.execution_bias == "BULLISH":
            self.market_bias = "STRONG_BULLISH"

        elif self.strategy_bias == "BEARISH" and self.execution_bias == "BEARISH":
            self.market_bias = "STRONG_BEARISH"

        elif self.strategy_bias == "BULLISH":
            self.market_bias = "BULLISH"

        elif self.strategy_bias == "BEARISH":
            self.market_bias = "BEARISH"

        else:
            self.market_bias = "NEUTRAL"

    # ------------------------------
    # Public API
    # ------------------------------

    def update(self, position: Dict, strategy_side: Optional[str]):

        self.update_execution_bias(position)
        self.update_strategy_bias(strategy_side)
        self.compute_market_bias()

    def get(self):

        return {
            "market_bias": self.market_bias,
            "strategy_bias": self.strategy_bias,
            "execution_bias": self.execution_bias,
        }


# Global instance
market_bias_engine = MarketBiasEngine()