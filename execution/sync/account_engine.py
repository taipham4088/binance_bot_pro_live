import math
import time

from .models import AccountState


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

    def get_equity(self, asset="USDT"):
        v = self.state.balances.get(asset, 0)
        if v is None:
            return 0.0
        return float(v)

    def total_account_equity_usdt(
        self,
        *,
        btc_usdt: float | None = None,
        eth_usdt: float | None = None,
    ) -> float:
        """
        Dashboard-only: approximate account value in USDT terms from wallet balances.
        USDT/USDC treated 1:1 USD; BTC/ETH scaled by provided mark/last prices.
        Does not affect risk sizing (get_equity remains USDT-only).
        """
        total = 0.0

        def _w(asset: str) -> float:
            v = self.state.balances.get(asset)
            if v is None:
                return 0.0
            try:
                x = float(v)
            except (TypeError, ValueError):
                return 0.0
            return x if math.isfinite(x) else 0.0

        total += _w("USDT") + _w("USDC")

        bpx = btc_usdt
        if bpx is not None and math.isfinite(bpx) and bpx > 0:
            total += _w("BTC") * bpx

        epx = eth_usdt
        if epx is not None and math.isfinite(epx) and epx > 0:
            total += _w("ETH") * epx

        return float(total)
