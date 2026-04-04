from trading_core.risk.engine_types import RiskVerdict


def test_frozen_supremacy(risk_engine, risk_state, intent, net_position):
    risk_state.frozen = True

    decision = risk_engine.assess(intent, net_position, risk_state)

    assert decision.verdict == RiskVerdict.FREEZE
