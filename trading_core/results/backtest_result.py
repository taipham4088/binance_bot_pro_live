class BacktestResult:
    def __init__(self, trades, equity_curve, stats=None):
        self.trades = trades
        self.equity_curve = equity_curve
        self.stats = stats or {}
