from datetime import date, timedelta
from trading_core.risk.supervisor import RiskSupervisor
from trading_core.risk.state import RiskState


def make_state():
    return RiskState(
        equity=1000,
        balance=950,
        realized_pnl=-50,
        unrealized_pnl=0,
        peak_equity=1100,
        trading_day=date.today(),
        day_start_balance=1000,
        daily_pnl=-50,
        daily_drawdown=50,
        session_drawdown=100,
        max_drawdown=120,
        trades_today=5,
        reverses_today=2,
        exposure_by_symbol={}
    )


def test_rollover_day_reset():
    sup = RiskSupervisor(make_state())
    sup.rollover_day(date.today() + timedelta(days=1))

    s = sup.snapshot()
    assert s.trading_day != date.today()
    assert s.daily_pnl == 0
    assert s.daily_drawdown == 0
    assert s.trades_today == 0
    assert s.daily_stop_triggered is False
