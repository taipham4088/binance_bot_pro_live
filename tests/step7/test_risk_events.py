from trading_core.risk.supervisor import RiskSupervisor
from trading_core.risk.state import RiskState
from trading_core.risk.reason import RiskReason
from trading_core.risk.events import RiskEventType
from datetime import date


def make_state():
    return RiskState(
        equity=1000,
        balance=1000,
        realized_pnl=0,
        unrealized_pnl=0,
        peak_equity=1000,
        trading_day=date.today(),
        day_start_balance=1000,
        daily_pnl=0,
        daily_drawdown=0,
        session_drawdown=0,
        max_drawdown=0,
        exposure_by_symbol={}
    )


def test_event_on_freeze():
    sup = RiskSupervisor(make_state())
    sup.manual_freeze(RiskReason.SYSTEM_RISK)

    events = sup.events()
    assert events[-1].type == RiskEventType.FREEZE
