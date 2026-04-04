from trading_core.risk.supervisor import RiskSupervisor
from trading_core.risk.reason import RiskReason
from trading_core.risk.state import RiskState
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


def test_trigger_daily_stop():
    sup = RiskSupervisor(make_state())
    sup.trigger_daily_stop()

    s = sup.snapshot()
    assert s.daily_stop_triggered is True
    assert s.daily_stop_days == 1


def test_trigger_dd_block():
    sup = RiskSupervisor(make_state())
    sup.trigger_dd_block()

    s = sup.snapshot()
    assert s.dd_block_triggered is True
    assert s.dd_block_days == 1


def test_manual_freeze():
    sup = RiskSupervisor(make_state())
    sup.manual_freeze(RiskReason.SYSTEM_RISK)

    s = sup.snapshot()
    assert s.frozen is True
