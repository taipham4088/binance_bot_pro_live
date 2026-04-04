from collections import deque


class StreamingSideBiasEngine:

    def __init__(self, window=50):
        self.window = window
        self.recent_trades = deque(maxlen=window)
        self.current_state = "NONE"

    def on_trade(self, trade):

        self.recent_trades.append(trade)

        if len(self.recent_trades) < self.window:
            self.current_state = "NONE"
            return self.current_state

        long_pnl = sum(t["result"] for t in self.recent_trades if t["side"] == "LONG")
        short_pnl = sum(t["result"] for t in self.recent_trades if t["side"] == "SHORT")

        if long_pnl > short_pnl * 1.5:
            self.current_state = "LONG_BIAS"
        elif short_pnl > long_pnl * 1.5:
            self.current_state = "SHORT_BIAS"
        else:
            self.current_state = "NEUTRAL"

        return self.current_state
