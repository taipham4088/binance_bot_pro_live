from trading_core.risk.control import RiskControlManager
from trading_core.risk.active_limits import ActiveRiskLimits
from trading_core.risk.commands import RiskCommand, RiskCommandType


def test_update_limits(risk_supervisor):

    active = ActiveRiskLimits()
    manager = RiskControlManager(risk_supervisor, active)

    cmd = RiskCommand(
        type=RiskCommandType.UPDATE_LIMITS,
        source="dashboard",
        daily_stop_pct=0.01,
        daily_dd_block_pct=0.05,
        max_position_size=0.2,
        max_trades_per_day=5
    )

    manager.handle(cmd)

    assert active.daily_stop_pct == 0.01
    assert active.daily_dd_block_pct == 0.05
    assert active.max_position_size == 0.2
    assert active.max_trades_per_day == 5
