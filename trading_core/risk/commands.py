from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set


class RiskCommandType(str, Enum):
    UPDATE_LIMITS = "UPDATE_LIMITS"
    FREEZE = "FREEZE"
    UNFREEZE = "UNFREEZE"
    SAFE_MODE = "SAFE_MODE"


@dataclass
class RiskCommand:
    type: RiskCommandType
    source: str                 # dashboard / system / admin
    daily_stop_pct: Optional[float] = None
    daily_dd_block_pct: Optional[float] = None
    max_position_size: Optional[float] = None
    max_notional: Optional[float] = None
    max_trades_per_day: Optional[int] = None
    allowed_symbols: Optional[Set[str]] = None
    safe_mode: Optional[bool] = None
    reason: Optional[str] = None
