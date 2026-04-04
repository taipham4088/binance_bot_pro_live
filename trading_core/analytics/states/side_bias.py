class SideBiasEngine:
    def infer(self, trades, window=50):

        if len(trades) < window:
            return "NONE"

        recent = trades[-window:]

        long_pnl = sum(t["result"] for t in recent if t["side"] == "LONG")
        short_pnl = sum(t["result"] for t in recent if t["side"] == "SHORT")

        if long_pnl > short_pnl * 1.5:
            return "LONG_BIAS"
        if short_pnl > long_pnl * 1.5:
            return "SHORT_BIAS"

        return "NEUTRAL"
