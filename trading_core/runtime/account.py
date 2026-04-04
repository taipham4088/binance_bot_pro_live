class AccountState:
    def __init__(self, initial_balance: float):
        self.initial_balance = initial_balance
        self.equity = initial_balance

        self.daily_loss_count = 0
        self.daily_start_balance = initial_balance
        self.current_day = None
        self.blocked_until = None

    def reset_day(self, day):
        self.current_day = day
        self.daily_loss_count = 0
        self.daily_start_balance = self.equity

    def daily_dd(self):
        return (self.daily_start_balance - self.equity) / self.daily_start_balance
