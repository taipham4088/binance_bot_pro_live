from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional

from trading_core.risk.reason import RiskReason


@dataclass
class RiskState:
    # -------- equity & pnl truth --------
    equity: float
    balance: float

    realized_pnl: float
    unrealized_pnl: float

    peak_equity: float

    # -------- daily tracking --------
    trading_day: date
    day_start_balance: float

    daily_pnl: float
    daily_drawdown: float

    # -------- drawdown tracking --------
    session_drawdown: float
    max_drawdown: float

    # -------- protection flags --------
    daily_stop_triggered: bool = False
    dd_block_triggered: bool = False

    daily_stop_days: int = 0
    dd_block_days: int = 0

    # -------- activity telemetry --------
    trades_today: int = 0
    reverses_today: int = 0
    last_trade_ts: Optional[float] = None

    # -------- exposure snapshot --------
    exposure_by_symbol: Dict[str, float] = field(default_factory=dict)

    # -------- system power --------
    frozen: bool = False
    freeze_reason: Optional[RiskReason] = None

    # -------- helpers --------

    def mark_daily_stop(self):
        self.daily_stop_triggered = True
        self.daily_stop_days += 1

    def mark_dd_block(self):
        self.dd_block_triggered = True
        self.dd_block_days += 1

    def freeze(self, reason: RiskReason):
        self.frozen = True
        self.freeze_reason = reason
