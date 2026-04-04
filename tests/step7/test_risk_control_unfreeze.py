from trading_core.risk.control import RiskControlManager
from trading_core.risk.active_limits import ActiveRiskLimits
from trading_core.risk.commands import RiskCommand, RiskCommandType
from trading_core.risk.reason import RiskReason


def test_manual_unfreeze_normal(risk_supervisor):

    active = ActiveRiskLimits()
    manager = RiskControlManager(risk_supervisor, active)

    # freeze trước
    manager.handle(RiskCommand(
        type=RiskCommandType.FREEZE,
        source="dashboard"
    ))

    # unfreeze
    manager.handle(RiskCommand(
        type=RiskCommandType.UNFREEZE,
        source="dashboard"
    ))

    state = risk_supervisor.snapshot()
    assert state.frozen is False


def test_unfreeze_blocked_when_dd_block(risk_supervisor):

    active = ActiveRiskLimits()
    manager = RiskControlManager(risk_supervisor, active)

    # giả lập DD block
    sup_state = risk_supervisor._get_state_ref()
    sup_state.dd_block_triggered = True
    sup_state.frozen = True
    sup_state.freeze_reason = RiskReason.DAILY_DD_BLOCK

    manager.handle(RiskCommand(
        type=RiskCommandType.UNFREEZE,
        source="dashboard"
    ))

    state = risk_supervisor.snapshot()
    assert state.frozen is True
