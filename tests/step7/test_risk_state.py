from datetime import date
from trading_core.risk.state import RiskState


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


def test_risk_state_init():
    s = make_state()
    assert s.equity == 1000
    assert s.peak_equity == 1000
    assert s.daily_stop_triggered is False
    assert s.dd_block_triggered is False
