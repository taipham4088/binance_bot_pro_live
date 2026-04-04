from enum import Enum
from dataclasses import dataclass


class MarketMode(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    DUAL = "DUAL"
    NEUTRAL = "NEUTRAL"


@dataclass
class MarketModeState:
    mode: MarketMode
    side_bias: str | None
    confidence: float
    reason: str | None
    ts: int
