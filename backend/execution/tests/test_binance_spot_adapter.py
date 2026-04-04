# =====================================================================
# ⚠ LEGACY DECISION ENGINE – NOT USED IN PRODUCTION FLOW
#
# This module belongs to the old execution decision engine.
# The current production architecture uses:
#   - backend/core/*
#   - execution/live_execution_system.py
#
# DO NOT import this module into backend/core or WS flow.
# =====================================================================
from backend.execution.adapter.binance.binance_spot_adapter import BinanceSpotAdapter
from backend.execution.types.execution_state import ExecutionState
from backend.execution.types.execution_plan import ExecutionPlan
from backend.execution.decision.decision_types import ExecutionPlanType


# -----------------------------
# MOCK CLIENT (READ-ONLY)
# -----------------------------
class MockBinanceSpotClient:
    def get_account(self):
        return {
            "balance": 1000,
            "available": 900,
        }

    def get_position(self):
        # Spot: chỉ có asset hoặc không
        return {
            "side": "long",
            "size": 0.01,
            "entry_price": 50000,
        }


def make_state(authority="live-readonly"):
    return ExecutionState(
        meta={},
        authority=authority,
        health="normal",
        execution_state="IDLE",
        position={"side": "flat", "size": 0},
        risk={},
        last_decision={},
    )


# -----------------------------
# TESTS
# -----------------------------

def test_spot_mapping_position():
    adapter = BinanceSpotAdapter(
        client=MockBinanceSpotClient(),
        symbol="BTCUSDT",
    )

    pos = adapter.sync_position()

    assert pos["side"] == "long"
    assert pos["size"] > 0


def test_readonly_does_not_execute():
    adapter = BinanceSpotAdapter(
        client=MockBinanceSpotClient(),
        symbol="BTCUSDT",
    )

    state = make_state(authority="live-readonly")
    plan = ExecutionPlan(
        plan=ExecutionPlanType.OPEN_POSITION,
        reason="test",
        source="manual",
        timestamp=0,
    )

    new_state = adapter.execute(plan, state)

    # Read-only → state không đổi
    assert new_state.execution_state == state.execution_state
    assert new_state.position == state.position


def test_no_reverse_logic_in_adapter():
    adapter = BinanceSpotAdapter(
        client=MockBinanceSpotClient(),
        symbol="BTCUSDT",
    )

    state = make_state(authority="live-trade")
    state.position = {"side": "long", "size": 1}

    plan = ExecutionPlan(
        plan=ExecutionPlanType.OPEN_POSITION,
        reason="should not reverse",
        source="manual",
        timestamp=0,
    )

    new_state = adapter.execute(plan, state)

    # Adapter không được tự reverse
    assert new_state.position["side"] == "long"
