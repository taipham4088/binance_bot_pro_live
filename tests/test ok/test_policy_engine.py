import pytest
import uuid

from trading_core.execution_policy.policy_engine import ExecutionPolicyEngine
from trading_core.execution_policy.intent_schema import ExecutionIntent, IntentType
from trading_core.execution_policy.net_position import NetPosition, PositionSide


# ===== helpers =====

def make_intent(type, side=None, qty=None, source="strategy"):
    return ExecutionIntent(
        intent_id=str(uuid.uuid4()),
        symbol="BTCUSDT",
        type=type,
        side=side,
        qty=qty,
        source=source
    )


FLAT = NetPosition(PositionSide.FLAT, 0)
LONG_1 = NetPosition(PositionSide.LONG, 1)
SHORT_1 = NetPosition(PositionSide.SHORT, 1)


# ===== tests =====

def test_allow_open_from_flat():
    engine = ExecutionPolicyEngine()
    intent = make_intent(IntentType.SET_POSITION, "LONG", 1)

    decision = engine.evaluate_intent(intent, FLAT)

    assert decision.decision == "ALLOW"
    assert decision.transition == "OPEN"
    assert decision.target.side == PositionSide.LONG
    assert decision.target.size == 1


def test_noop_refused():
    engine = ExecutionPolicyEngine()
    intent = make_intent(IntentType.SET_POSITION, "LONG", 1)

    decision = engine.evaluate_intent(intent, LONG_1)

    assert decision.decision == "REFUSE"
    assert "NOOP" in decision.reason


def test_reverse_allowed():
    engine = ExecutionPolicyEngine()
    intent = make_intent(IntentType.SET_POSITION, "SHORT", 1)

    decision = engine.evaluate_intent(intent, LONG_1)

    assert decision.decision == "ALLOW"
    assert decision.transition == "REVERSE"
    assert decision.target.side == PositionSide.SHORT


def test_close_allowed():
    engine = ExecutionPolicyEngine()
    intent = make_intent(IntentType.SET_FLAT)

    decision = engine.evaluate_intent(intent, LONG_1)

    assert decision.decision == "ALLOW"
    assert decision.transition == "CLOSE"
    assert decision.target.side == PositionSide.FLAT


def test_illegal_intent_refused():
    engine = ExecutionPolicyEngine()
    intent = make_intent(IntentType.SET_POSITION, "LONG", 0)

    decision = engine.evaluate_intent(intent, FLAT)

    assert decision.decision == "REFUSE"


def test_emergency_from_strategy_freeze():
    engine = ExecutionPolicyEngine()
    intent = make_intent(IntentType.EMERGENCY, source="strategy")

    decision = engine.evaluate_intent(intent, FLAT)

    assert decision.decision == "FREEZE"


def test_emergency_from_system_allowed():
    engine = ExecutionPolicyEngine()
    intent = make_intent(IntentType.EMERGENCY, source="system")

    decision = engine.evaluate_intent(intent, FLAT)

    assert decision.decision == "ALLOW"
