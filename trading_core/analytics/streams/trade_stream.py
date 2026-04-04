class TradeStream:
    def __init__(self, trades):
        self.trades = trades

    def wins(self):
        return [t for t in self.trades if t["result"] > 0]

    def losses(self):
        return [t for t in self.trades if t["result"] <= 0]

    def by_side(self, side):
        return [t for t in self.trades if t["side"] == side]
