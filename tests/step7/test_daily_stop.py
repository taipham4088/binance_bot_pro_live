from trading_core.risk.limits import RiskLimits
from trading_core.risk.engine import RiskEngine
from trading_core.risk.engine_types import RiskVerdict


def test_symbol_not_allowed(intent, net_position, risk_state):
    limits = RiskLimits(allowed_symbols={"BTCUSDT"})
    engine = RiskEngine(limits)

    intent.symbol = "ETHUSDT"

    decision = engine.assess(intent, net_position, risk_state)

    assert decision.verdict == RiskVerdict.REFUSE
