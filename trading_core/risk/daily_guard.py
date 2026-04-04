from trading_core.risk.engine_types import RiskDecision, RiskVerdict
from trading_core.risk.reason import RiskReason
from trading_core.risk.state import RiskState


class RiskDailyGuard:
    """
    STEP 7 – Phase 7.3

    - daily stop  -> REFUSE
    - dd block    -> FREEZE
    """

    def assess(self, risk_state: RiskState) -> RiskDecision:

        if risk_state.dd_block_triggered:
            return RiskDecision(
                RiskVerdict.FREEZE,
                RiskReason.DAILY_DD_BLOCK,
                "daily drawdown block triggered"
            )

        if risk_state.daily_stop_triggered:
            return RiskDecision(
                RiskVerdict.REFUSE,
                RiskReason.DAILY_STOP,
                "daily stop triggered"
            )

        return RiskDecision(RiskVerdict.ALLOW, None, None)
