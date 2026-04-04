from dataclasses import dataclass
from typing import Optional, Set


@dataclass
class ActiveRiskLimits:
    daily_stop_pct: Optional[float] = None
    daily_dd_block_pct: Optional[float] = None
    max_position_size: Optional[float] = None
    max_notional: Optional[float] = None
    max_trades_per_day: Optional[int] = None
    allowed_symbols: Optional[Set[str]] = None
    safe_mode: bool = False

    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k) and v is not None:
                setattr(self, k, v)
