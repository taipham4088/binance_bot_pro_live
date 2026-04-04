from typing import Optional

from backend.risk.risk_state import RiskState
from backend.risk.risk_rules import (
    RiskRuleEngine,
    KillSwitchRule,
    MaxPositionSizeRule,
    TradeFrequencyRule,
    DailyLossRule,
    RiskDecision,
)


class RiskEngine:
    """
    Central risk control layer for the trading system.

    Responsibilities:
    - Maintain RiskState
    - Evaluate trading intents
    - Update risk statistics
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(
        self,
        max_position_size: float = 0.05,
        max_trades_per_hour: int = 5,
        max_daily_loss: float = 200,
        starting_equity: float = 10000,
    ):

        # Runtime risk state
        self.state = RiskState(starting_equity=starting_equity)

        # Risk rules
        rules = [
            KillSwitchRule(),
            DailyLossRule(max_daily_loss),
            MaxPositionSizeRule(max_position_size),
            TradeFrequencyRule(max_trades_per_hour),
        ]

        self.rule_engine = RiskRuleEngine(rules)

    # =====================================================
    # INTENT EVALUATION
    # =====================================================

    def evaluate_intent(self, intent) -> RiskDecision:
        """
        Evaluate trading intent before execution.

        Returns RiskDecision.
        """

        decision = self.rule_engine.evaluate(intent, self.state)

        if not decision.allowed:

            print(
                f"[RISK BLOCK] intent={intent.type} "
                f"reason={decision.reason}"
            )

        return decision

    # =====================================================
    # TRADE EVENT
    # =====================================================

    def on_trade_executed(self, intent):
        """
        Update risk statistics when a trade is executed.
        """

        if intent.type.startswith("open"):
            self.state.register_trade()

        qty = intent.payload.get("qty", 0)

        if intent.type.startswith("open"):
            new_size = self.state.current_position_size + qty
            self.state.update_position(new_size)

        elif intent.type.startswith("close"):
            self.state.update_position(0)

    # =====================================================
    # EQUITY UPDATE
    # =====================================================

    def update_equity(self, equity: float):
        """
        Update account equity for PnL based rules.
        """
        self.state.update_equity(equity)

    # =====================================================
    # MANUAL CONTROLS
    # =====================================================

    def activate_kill_switch(self):

        self.state.activate_kill_switch()

        print("[RISK] kill switch activated")

    def reset_kill_switch(self):

        self.state.reset_kill_switch()

        print("[RISK] kill switch reset")

    # =====================================================
    # STATE SNAPSHOT
    # =====================================================

    def snapshot(self):

        return self.state.snapshot()

    # =====================================================
    # DEBUG STATUS
    # =====================================================

    def print_status(self):

        snap = self.snapshot()

        print("[RISK STATUS]")
        print(f" equity = {snap['equity']}")
        print(f" daily_pnl = {snap['daily_pnl']}")
        print(f" trades_today = {snap['trade_count_today']}")
        print(f" trades_hour = {snap['trade_count_hour']}")
        print(f" position_size = {snap['current_position_size']}")
        print(f" kill_switch = {snap['kill_switch']}")