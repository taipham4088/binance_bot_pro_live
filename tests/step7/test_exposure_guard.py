from trading_core.risk.limits import RiskLimits
from trading_core.risk.engine import RiskEngine
from trading_core.risk.engine_types import RiskVerdict


def test_max_position_size(intent, net_position, risk_state):
    limits = RiskLimits(max_position_size=0.1)
    engine = RiskEngine(limits)

    intent.target_size = 0.2

    decision = engine.assess(intent, net_position, risk_state)

    assert decision.verdict == RiskVerdict.REFUSE
