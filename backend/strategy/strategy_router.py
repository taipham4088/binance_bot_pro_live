from .trend_strategy import TrendStrategy
from .momentum_strategy import MomentumStrategy


class StrategyRouter:

    def __init__(self):

        self._strategies = {
            "trend": TrendStrategy(),
            "momentum": MomentumStrategy()
        }

        self._active = "trend"

    # =========================
    # dashboard control
    # =========================

    def set_active_strategy(self, name):

        if name not in self._strategies:
            raise ValueError("unknown strategy")

        self._active = name

    def get_active_strategy(self):
        return self._active

    # =========================
    # execution entry
    # =========================

    def generate_intent(self, market_state):

        strategy = self._strategies[self._active]

        return strategy.generate_intent(market_state)
