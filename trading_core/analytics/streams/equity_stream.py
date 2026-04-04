class EquityStream:
    def __init__(self, equity_curve):
        self.times = [t for t, _ in equity_curve]
        self.values = [v for _, v in equity_curve]

    def returns(self):
        return [
            (self.values[i] - self.values[i-1]) / self.values[i-1]
            for i in range(1, len(self.values))
        ]

    def max_equity(self):
        out = []
        cur = self.values[0]
        for v in self.values:
            cur = max(cur, v)
            out.append(cur)
        return out
