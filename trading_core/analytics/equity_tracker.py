class EquityTracker:
    def __init__(self, initial_balance: float):
        self.curve = [(None, initial_balance)]

    def update(self, time, equity):
        self.curve.append((time, equity))
