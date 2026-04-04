from dataclasses import dataclass
from enum import Enum


class PositionSide(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class NetPosition:
    side: PositionSide
    size: float

    def validate(self):
        if self.side == PositionSide.FLAT:
            if self.size != 0:
                raise ValueError("FLAT position must have size = 0")
        else:
            if self.size <= 0:
                raise ValueError("LONG/SHORT must have size > 0")

    def is_flat(self) -> bool:
        return self.side == PositionSide.FLAT and self.size == 0
