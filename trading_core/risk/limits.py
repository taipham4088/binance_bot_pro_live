from dataclasses import dataclass
from typing import Optional, Set


@dataclass(frozen=True)
class RiskLimits:
    # -------- core protections --------
    daily_stop_pct: Optional[float] = None
    daily_dd_block_pct: Optional[float] = None

    # -------- exposure law (future) --------
    max_position_size: Optional[float] = None
    max_notional: Optional[float] = None

    # -------- frequency law (future) --------
    max_trades_per_day: Optional[int] = None
    min_trade_interval_sec: Optional[int] = None

    # -------- symbol law --------
    allowed_symbols: Optional[Set[str]] = None
