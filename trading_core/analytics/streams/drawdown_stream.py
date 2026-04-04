class DrawdownStream:
    def __init__(self, equity_stream):
        self.equity = equity_stream.values
        self.max_curve = equity_stream.max_equity()
        self.dd = [
            (self.max_curve[i] - self.equity[i]) / self.max_curve[i]
            for i in range(len(self.equity))
        ]

    def max_dd(self):
        return max(self.dd)

    def last(self):
        return self.dd[-1]
