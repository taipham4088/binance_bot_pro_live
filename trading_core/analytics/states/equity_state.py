class EquityStateEngine:
    def __init__(self, lookback=50,
                 danger_dd=0.12,
                 expansion_slope=0.002):

        self.lookback = lookback
        self.danger_dd = danger_dd
        self.expansion_slope = expansion_slope

    def infer(self, equity_stream, dd_stream):

        if len(equity_stream.values) < self.lookback:
            return "NEUTRAL"

        recent = equity_stream.values[-self.lookback:]

        slope = (recent[-1] - recent[0]) / recent[0]
        last_dd = dd_stream.last()

        if last_dd >= self.danger_dd:
            return "DANGER"

        if slope > self.expansion_slope:
            return "EXPANSION"

        return "NEUTRAL"
