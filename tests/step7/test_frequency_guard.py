from trading_core.risk.limits import RiskLimits
from trading_core.risk.engine import RiskEngine
from trading_core.risk.engine_types import RiskVerdict


def test_max_trades_per_day(intent, net_position, risk_state):
    limits = RiskLimits(max_trades_per_day=3)
    engine = RiskEngine(limits)

    risk_state.trades_today = 3

    decision = engine.assess(intent, net_position, risk_state)

    assert decision.verdict == RiskVerdict.REFUSE
