from dataclasses import dataclass


@dataclass(frozen=True)
class TargetState:
    symbol: str
    side: str
    qty: float
