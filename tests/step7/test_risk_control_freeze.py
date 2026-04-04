from trading_core.risk.control import RiskControlManager
from trading_core.risk.active_limits import ActiveRiskLimits
from trading_core.risk.commands import RiskCommand, RiskCommandType


def test_manual_freeze(risk_supervisor):

    active = ActiveRiskLimits()
    manager = RiskControlManager(risk_supervisor, active)

    cmd = RiskCommand(
        type=RiskCommandType.FREEZE,
        source="dashboard",
        reason="manual kill"
    )

    manager.handle(cmd)

    state = risk_supervisor.snapshot()
    assert state.frozen is True
