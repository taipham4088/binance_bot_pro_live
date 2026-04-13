"""Stub router on TradingSession. Live/paper/backtest entries use trading_core DualEngine."""

_LEGACY = frozenset({"range", "trend", "momentum", "dual_engine"})
_ACTIVE_RANGE_TREND_KEYS = frozenset(
    {
        "range_trend",
        "range_trend_1m",
        "range_trend_15m",
        "range_trend_1h",
    }
)
ACTIVE = "range_trend"


class StrategyRouter:

    def __init__(self):
        self._active = ACTIVE

    def set_active_strategy(self, name: str):
        n = (name or ACTIVE).strip().lower()
        if n in _LEGACY:
            n = ACTIVE
        if n not in _ACTIVE_RANGE_TREND_KEYS:
            raise ValueError(
                "unknown strategy: expected one of "
                + ", ".join(sorted(_ACTIVE_RANGE_TREND_KEYS))
            )
        self._active = n

    def get_active_strategy(self):
        return self._active

    def generate_intent(self, market_state):
        return None
