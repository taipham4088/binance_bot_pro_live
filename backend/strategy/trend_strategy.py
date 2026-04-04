from .base_strategy import BaseStrategy
from .engines.long_engine import process_long, init_long_state
from .engines.short_engine import process_short, init_short_state


class TrendStrategy(BaseStrategy):

    name = "trend"

    def __init__(self):
        self.long_state = init_long_state()
        self.short_state = init_short_state()

    def generate_intent(self, market_state):

        i = market_state["index"]
        row = market_state["row"]
        df = market_state["df"]
        equity = market_state.get("equity", 10000)

        long_signal = process_long(
            i,
            row,
            df,
            self.long_state,
            equity
        )

        short_signal = process_short(
            i,
            row,
            df,
            self.short_state,
            equity
        )

        if long_signal and not short_signal:
            return {
                "side": "LONG",
                "qty": 0.01
            }

        if short_signal and not long_signal:
            return {
                "side": "SHORT",
                "qty": 0.01
            }

        return None
