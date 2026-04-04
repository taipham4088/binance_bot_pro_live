from .models import AccountState
import time


class AccountEngine:

    def __init__(self):
        self.state = AccountState()

    def apply_balance_snapshot(self, balances):
        for b in balances:
            self.state.balances[b.asset] = b.wallet
            self.state.available[b.asset] = b.available

        self.state.last_update = time.time()
        return self.state

    def apply_balance_event(self, balance):
        self.state.balances[balance.asset] = balance.wallet
        self.state.available[balance.asset] = balance.available
        self.state.last_update = time.time()
        return self.state
