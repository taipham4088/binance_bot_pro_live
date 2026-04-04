from trading_core.risk.limits import RiskLimits
from trading_core.risk.active_limits import ActiveRiskLimits


class RiskLimitResolver:
    """
    BaseRiskLimits  (code law)
    ActiveRiskLimits (dashboard law)

    => Effective limits used by engines
    """

    def __init__(self,
                 base: RiskLimits,
                 active: ActiveRiskLimits):
        self._base = base
        self._active = active

    def effective(self) -> RiskLimits:
        return RiskLimits(
            daily_stop_pct=self._pick(self._base.daily_stop_pct,
                                       self._active.daily_stop_pct),

            daily_dd_block_pct=self._pick(self._base.daily_dd_block_pct,
                                           self._active.daily_dd_block_pct),

            max_position_size=self._pick(self._base.max_position_size,
                                          self._active.max_position_size),

            max_notional=self._pick(self._base.max_notional,
                                     self._active.max_notional),

            max_trades_per_day=self._pick(self._base.max_trades_per_day,
                                           self._active.max_trades_per_day),

            min_trade_interval_sec=self._base.min_trade_interval_sec,
            allowed_symbols=self._active.allowed_symbols or self._base.allowed_symbols
        )

    @staticmethod
    def _pick(base, active):
        if base is None:
            return active
        if active is None:
            return base
        return min(base, active)
