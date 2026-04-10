"""Stub router on TradingSession. Live/paper/backtest entries use trading_core DualEngine."""

_LEGACY = frozenset({"range", "trend", "momentum", "dual_engine"})
ACTIVE = "range_trend"


class StrategyRouter:

    def __init__(self):
        self._active = ACTIVE

    def set_active_strategy(self, name: str):
        n = (name or ACTIVE).strip().lower()
        if n in _LEGACY:
            n = ACTIVE
        if n != ACTIVE:
            raise ValueError("unknown strategy: only range_trend is supported")
        self._active = n

    def get_active_strategy(self):
        return self._active

    def generate_intent(self, market_state):
        return None
