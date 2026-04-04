import pytest

from trading_core.execution_policy.position_projector import *
from trading_core.execution_policy.net_position import PositionSide
from trading_core.execution_policy.policy_engine import ExecutionPolicyEngine

def test_flat():
    p = NetPositionProjector()
    net = p.project([])
    assert net.side == PositionSide.FLAT
    assert net.size == 0


def test_long():
    p = NetPositionProjector()
    net = p.project([
        {"positionAmt": "0.5"}
    ])
    assert net.side == PositionSide.LONG
    assert net.size == 0.5


def test_short():
    p = NetPositionProjector()
    net = p.project([
        {"positionAmt": "-0.3"}
    ])
    assert net.side == PositionSide.SHORT
    assert net.size == 0.3


def test_merge_long():
    p = NetPositionProjector()
    net = p.project([
        {"positionAmt": "0.2"},
        {"positionAmt": "0.3"}
    ])
    assert net.side == PositionSide.LONG
    assert net.size == 0.5


def test_hedge_detected():
    p = NetPositionProjector()
    with pytest.raises(PositionProjectionError):
        p.project([
            {"positionAmt": "0.5"},
            {"positionAmt": "-0.2"}
        ])
