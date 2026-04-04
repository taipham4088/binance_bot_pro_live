import time
from typing import Optional

from trading_core.risk.state import RiskState
from trading_core.risk.limits import RiskLimits
from trading_core.risk.reason import RiskReason
from trading_core.risk.engine_types import RiskVerdict, RiskDecision


class RiskEngine:
    """
    STEP 7 – Phase 7.2
    Supreme Risk Court.

    Enforces:
    - frozen supremacy
    - symbol law
    - exposure law
    - frequency law

    Does NOT handle:
    - daily stop
    - drawdown block
    """

    def __init__(self, limits: RiskLimits):
        self._limits = limits

    # ---------- public entry ----------

    def assess(self, intent, net_position, risk_state: RiskState) -> RiskDecision:
        """
        intent: ExecutionIntent (absolute target)
        net_position: NetPosition (from Step 6)
        risk_state: RiskState (truth)
        """

        # 1. frozen supremacy
        if risk_state.frozen:
            return RiskDecision(
                RiskVerdict.FREEZE,
                risk_state.freeze_reason or RiskReason.SYSTEM_RISK,
                "system is frozen"
            )

        # 2. symbol law
        decision = self._check_symbol(intent)
        if decision:
            return decision

        # 3. exposure law
        decision = self._check_exposure(intent, net_position, risk_state)
        if decision:
            return decision

        # 4. frequency law
        decision = self._check_frequency(intent, risk_state)
        if decision:
            return decision

        return RiskDecision(RiskVerdict.ALLOW, None, None)

    # ---------- guards ----------

    def _check_symbol(self, intent) -> Optional[RiskDecision]:
        if self._limits.allowed_symbols is None:
            return None

        if intent.symbol not in self._limits.allowed_symbols:
            return RiskDecision(
                RiskVerdict.REFUSE,
                RiskReason.SYSTEM_RISK,
                f"symbol {intent.symbol} not allowed"
            )

        return None

    def _check_exposure(self, intent, net_position, risk_state) -> Optional[RiskDecision]:
        """
        intent phải đã là absolute net target (sau Step 6 QuantityPolicy)
        """

        target_size = abs(intent.target_size)

        if self._limits.max_position_size is not None:
            if target_size > self._limits.max_position_size:
                return RiskDecision(
                    RiskVerdict.REFUSE,
                    RiskReason.SYSTEM_RISK,
                    f"target size {target_size} > max {self._limits.max_position_size}"
                )

        if self._limits.max_notional is not None:
            if intent.mark_price is None:
                return RiskDecision(
                    RiskVerdict.FREEZE,
                    RiskReason.SYSTEM_RISK,
                    "missing mark price for notional check"
                )

            notional = target_size * intent.mark_price
            if notional > self._limits.max_notional:
                return RiskDecision(
                    RiskVerdict.REFUSE,
                    RiskReason.SYSTEM_RISK,
                    f"notional {notional} > max {self._limits.max_notional}"
                )

        return None

    def _check_frequency(self, intent, risk_state: RiskState) -> Optional[RiskDecision]:

        # max trades / day
        if self._limits.max_trades_per_day is not None:
            if risk_state.trades_today >= self._limits.max_trades_per_day:
                return RiskDecision(
                    RiskVerdict.REFUSE,
                    RiskReason.SYSTEM_RISK,
                    "max trades per day reached"
                )

        # min trade interval
        if self._limits.min_trade_interval_sec is not None:
            if risk_state.last_trade_ts is not None:
                delta = time.time() - risk_state.last_trade_ts
                if delta < self._limits.min_trade_interval_sec:
                    return RiskDecision(
                        RiskVerdict.REFUSE,
                        RiskReason.SYSTEM_RISK,
                        f"trade too frequent: {delta:.2f}s"
                    )

        return None
