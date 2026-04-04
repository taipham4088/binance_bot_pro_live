import pytest

from trading_core.execution_policy.transitions import (
    TransitionValidator,
    TransitionType
)

from trading_core.execution_policy.net_position import (
    NetPosition,
    PositionSide
)


# ===== helpers =====

FLAT = NetPosition(PositionSide.FLAT, 0)
LONG_1 = NetPosition(PositionSide.LONG, 1)
LONG_2 = NetPosition(PositionSide.LONG, 2)
SHORT_1 = NetPosition(PositionSide.SHORT, 1)
SHORT_2 = NetPosition(PositionSide.SHORT, 2)


# ===== tests =====

def test_noop():
    tv = TransitionValidator()
    assert tv.classify(FLAT, FLAT) == TransitionType.NOOP
    assert tv.classify(LONG_1, LONG_1) == TransitionType.NOOP


def test_open():
    tv = TransitionValidator()
    assert tv.classify(FLAT, LONG_1) == TransitionType.OPEN
    assert tv.classify(FLAT, SHORT_1) == TransitionType.OPEN


def test_close():
    tv = TransitionValidator()
    assert tv.classify(LONG_1, FLAT) == TransitionType.CLOSE
    assert tv.classify(SHORT_1, FLAT) == TransitionType.CLOSE


def test_reverse():
    tv = TransitionValidator()
    assert tv.classify(LONG_1, SHORT_1) == TransitionType.REVERSE
    assert tv.classify(SHORT_1, LONG_1) == TransitionType.REVERSE


def test_adjust_same_side():
    tv = TransitionValidator()
    assert tv.classify(LONG_1, LONG_2) == TransitionType.ADJUST
    assert tv.classify(SHORT_1, SHORT_2) == TransitionType.ADJUST


def test_illegal():
    tv = TransitionValidator()
    with pytest.raises(ValueError):
        tv.classify(FLAT, NetPosition(PositionSide.FLAT, 1))
