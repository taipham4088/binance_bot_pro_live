from trading_core.runtime.account import AccountState
from backend.ports.account_port import AccountPort


class PaperAccountAdapter(AccountPort):

    def __init__(self, initial_balance: float):
        self.state = AccountState(initial_balance)
        self._mock_equity = None

    # ===== core queries =====

    def get_balance(self):
        return self.state.initial_balance

    def get_equity(self):
        if self._mock_equity is not None:
            return self._mock_equity
        return self.state.equity

    def get_state(self):
        return self.state

    def get_positions(self):
        # paper mode: position đang do core quản lý
        return []

    # ===== risk & day control =====

    def reset_day(self, day):
        self.state.reset_day(day)

    def daily_dd(self):
        return self.state.daily_dd()

    def block_until(self, time):
        self.state.blocked_until = time

    # ===== trade result hooks =====

    def register_loss(self, amount: float):
        self.state.equity -= amount
        self.state.daily_loss_count += 1

    def register_win(self, amount: float):
        self.state.equity += amount

    # ===== dev / mock =====

    def set_mock_equity(self, equity: float):
        """
        DEV only: override equity for testing risk sizing
        """
        self._mock_equity = equity

