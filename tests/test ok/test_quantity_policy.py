import pytest
import uuid

from trading_core.execution_policy.quantity_policy import QuantityPolicy
from trading_core.execution_policy.intent_schema import ExecutionIntent, IntentType
from trading_core.execution_policy.net_position import NetPosition, PositionSide


# ===== helpers =====

def make_intent(type, side=None, qty=None):
    return ExecutionIntent(
        intent_id=str(uuid.uuid4()),
        symbol="BTCUSDT",
        type=type,
        side=side,
        qty=qty,
        source="strategy"
    )


FLAT = NetPosition(PositionSide.FLAT, 0)
LONG_1 = NetPosition(PositionSide.LONG, 1)
SHORT_1 = NetPosition(PositionSide.SHORT, 1)


# ===== tests =====

def test_set_flat():
    qp = QuantityPolicy()
    target = qp.map_intent_to_target(make_intent(IntentType.SET_FLAT), LONG_1)

    assert target.side == PositionSide.FLAT
    assert target.size == 0


def test_open_long_from_flat():
    qp = QuantityPolicy()
    target = qp.map_intent_to_target(make_intent(IntentType.SET_POSITION, "LONG", 1), FLAT)

    assert target.side == PositionSide.LONG
    assert target.size == 1


def test_open_short_from_flat():
    qp = QuantityPolicy()
    target = qp.map_intent_to_target(make_intent(IntentType.SET_POSITION, "SHORT", 2), FLAT)

    assert target.side == PositionSide.SHORT
    assert target.size == 2


def test_adjust_same_side():
    qp = QuantityPolicy()
    target = qp.map_intent_to_target(make_intent(IntentType.SET_POSITION, "LONG", 3), LONG_1)

    assert target.side == PositionSide.LONG
    assert target.size == 3


def test_reverse():
    qp = QuantityPolicy()
    target = qp.map_intent_to_target(make_intent(IntentType.SET_POSITION, "SHORT", 2), LONG_1)

    assert target.side == PositionSide.SHORT
    assert target.size == 2


def test_zero_qty_illegal():
    qp = QuantityPolicy()
    with pytest.raises(ValueError):
        qp.map_intent_to_target(make_intent(IntentType.SET_POSITION, "LONG", 0), FLAT)


def test_negative_qty_illegal():
    qp = QuantityPolicy()
    with pytest.raises(ValueError):
        qp.map_intent_to_target(make_intent(IntentType.SET_POSITION, "LONG", -1), FLAT)


def test_missing_side_illegal():
    qp = QuantityPolicy()
    with pytest.raises(ValueError):
        qp.map_intent_to_target(make_intent(IntentType.SET_POSITION, None, 1), FLAT)
