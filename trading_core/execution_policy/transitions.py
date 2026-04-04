from enum import Enum
from .net_position import PositionSide, NetPosition


class TransitionType(str, Enum):
    NOOP = "NOOP"
    OPEN = "OPEN"
    ADJUST = "ADJUST"
    CLOSE = "CLOSE"
    REVERSE = "REVERSE"
    ILLEGAL = "ILLEGAL"


class TransitionValidator:

    @staticmethod
    def classify(current: NetPosition, target: NetPosition) -> TransitionType:

        # ===== ILLEGAL STATES =====
        if target.side == PositionSide.FLAT and target.qty != 0:
            raise ValueError("ILLEGAL_TARGET_FLAT_NONZERO")

        if current.side == PositionSide.FLAT and current.size != 0:
            raise ValueError("ILLEGAL_CURRENT_FLAT_NONZERO")

        # NOOP
        if current.side == target.side and current.size == target.qty:
            return TransitionType.NOOP

        # FLAT → something
        if current.side == PositionSide.FLAT:
            if target.side in (PositionSide.LONG, PositionSide.SHORT):
                return TransitionType.OPEN
            return TransitionType.ILLEGAL

        # something → FLAT
        if target.side == PositionSide.FLAT:
            return TransitionType.CLOSE

        # same side replace
        if current.side == target.side:
            return TransitionType.ADJUST

        # reverse
        if current.side != target.side:
            return TransitionType.REVERSE

        return TransitionType.ILLEGAL
