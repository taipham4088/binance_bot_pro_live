from backend.ports.account_port import AccountPort
from trading_core.runtime.account import AccountState

class DummyAccountAdapter(AccountPort):

    def __init__(self, initial_balance: float):
        self.state = AccountState(initial_balance)

    def get_balance(self):
        return self.state.initial_balance

    def get_equity(self):
        return self.state.equity

    def get_state(self):
        return self.state

    def get_positions(self):
        return []

    def reset_day(self, day):
        self.state.reset_day(day)

    def daily_dd(self):
        return self.state.daily_dd()

    def block_until(self, time):
        self.state.blocked_until = time

    def register_loss(self, amount: float):
        self.state.equity -= amount
        self.state.daily_loss_count += 1

    def register_win(self, amount: float):
        self.state.equity += amount
