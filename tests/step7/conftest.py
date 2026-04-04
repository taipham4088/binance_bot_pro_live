import pytest
from datetime import date

from trading_core.risk.engine import RiskEngine
from trading_core.risk.limits import RiskLimits
from trading_core.risk.state import RiskState
from trading_core.risk.supervisor import RiskSupervisor


# -------- dummy objects for tests --------

class DummyIntent:
    def __init__(self):
        self.symbol = "BTCUSDT"
        self.target_size = 0.01
        self.mark_price = 50000


class DummyNetPosition:
    def __init__(self):
        self.size = 0.0


# -------- fixtures --------

@pytest.fixture
def risk_limits():
    return RiskLimits(
        max_position_size=1.0,
        max_trades_per_day=10,
        allowed_symbols={"BTCUSDT"}
    )


@pytest.fixture
def risk_engine(risk_limits):
    return RiskEngine(risk_limits)


@pytest.fixture
def risk_state():
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


@pytest.fixture
def intent():
    return DummyIntent()


@pytest.fixture
def net_position():
    return DummyNetPosition()

@pytest.fixture
def risk_supervisor():
    state = RiskState(
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
    return RiskSupervisor(state)
