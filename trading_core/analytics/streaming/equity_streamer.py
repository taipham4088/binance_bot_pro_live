from collections import deque


class StreamingEquityStateEngine:
    """
    Incremental equity + drawdown + regime state
    """

    def __init__(self, lookback=50, danger_dd=0.12, expansion_slope=0.002):
        self.lookback = lookback
        self.danger_dd = danger_dd
        self.expansion_slope = expansion_slope

        self.equity_window = deque(maxlen=lookback)
        self.max_equity = None
        self.last_dd = 0.0

        self.current_state = "NEUTRAL"

    def on_equity(self, time, equity):

        # update max equity
        if self.max_equity is None:
            self.max_equity = equity
        else:
            self.max_equity = max(self.max_equity, equity)

        # drawdown
        self.last_dd = (self.max_equity - equity) / self.max_equity
        self.equity_window.append(equity)

        # not enough data
        if len(self.equity_window) < self.lookback:
            self.current_state = "NEUTRAL"
            return self.current_state

        first = self.equity_window[0]
        last = self.equity_window[-1]
        slope = (last - first) / first

        if self.last_dd >= self.danger_dd:
            self.current_state = "DANGER"
        elif slope > self.expansion_slope:
            self.current_state = "EXPANSION"
        else:
            self.current_state = "NEUTRAL"

        return self.current_state
