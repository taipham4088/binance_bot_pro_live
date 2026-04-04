from dataclasses import dataclass
from typing import Optional
from backend.risk.risk_state import RiskState


# =====================================================
# Risk Decision
# =====================================================

@dataclass
class RiskDecision:
    allowed: bool
    reason: Optional[str] = None


# =====================================================
# Base Rule
# =====================================================

class BaseRiskRule:
    """
    Base class for all risk rules.
    """

    def evaluate(self, intent, state: RiskState) -> RiskDecision:
        raise NotImplementedError


# =====================================================
# Kill Switch Rule
# =====================================================

class KillSwitchRule(BaseRiskRule):
    """
    If kill switch is active, block all OPEN intents.
    CLOSE intents are always allowed.
    """

    def evaluate(self, intent, state: RiskState) -> RiskDecision:

        if state.kill_switch:

            if intent.type.startswith("close"):
                return RiskDecision(True)

            return RiskDecision(
                allowed=False,
                reason="kill_switch_active"
            )

        return RiskDecision(True)


# =====================================================
# Max Position Size Rule
# =====================================================

class MaxPositionSizeRule(BaseRiskRule):

    def __init__(self, max_position_size: float):
        self.max_position_size = max_position_size

    def evaluate(self, intent, state: RiskState) -> RiskDecision:

        if not intent.type.startswith("open"):
            return RiskDecision(True)

        qty = intent.payload.get("qty", 0)

        projected_position = state.current_position_size + qty

        if projected_position > self.max_position_size:

            return RiskDecision(
                allowed=False,
                reason="max_position_size_exceeded"
            )

        return RiskDecision(True)


# =====================================================
# Trade Frequency Rule
# =====================================================

class TradeFrequencyRule(BaseRiskRule):

    def __init__(self, max_trades_per_hour: int):
        self.max_trades_per_hour = max_trades_per_hour

    def evaluate(self, intent, state: RiskState) -> RiskDecision:

        if not intent.type.startswith("open"):
            return RiskDecision(True)

        if state.trade_count_hour >= self.max_trades_per_hour:

            return RiskDecision(
                allowed=False,
                reason="trade_frequency_limit"
            )

        return RiskDecision(True)


# =====================================================
# Daily Loss Rule
# =====================================================

class DailyLossRule(BaseRiskRule):

    def __init__(self, max_daily_loss: float):
        self.max_daily_loss = max_daily_loss

    def evaluate(self, intent, state: RiskState) -> RiskDecision:

        if state.daily_pnl <= -abs(self.max_daily_loss):

            state.activate_kill_switch()

            return RiskDecision(
                allowed=False,
                reason="daily_loss_limit_hit"
            )

        return RiskDecision(True)


# =====================================================
# Risk Rule Engine
# =====================================================

class RiskRuleEngine:
    """
    Evaluates all risk rules sequentially.
    """

    def __init__(self, rules):
        self.rules = rules

    def evaluate(self, intent, state: RiskState) -> RiskDecision:

        for rule in self.rules:

            decision = rule.evaluate(intent, state)

            if not decision.allowed:
                return decision

        return RiskDecision(True)