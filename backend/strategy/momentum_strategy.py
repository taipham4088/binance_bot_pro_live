from .base_strategy import BaseStrategy


class MomentumStrategy(BaseStrategy):

    name = "momentum"

    def generate_intent(self, market_state):

        momentum = market_state.get("momentum")

        if momentum == "BULL":
            return {
                "side": "LONG",
                "qty": 0.01
            }

        if momentum == "BEAR":
            return {
                "side": "SHORT",
                "qty": 0.01
            }

        return None
