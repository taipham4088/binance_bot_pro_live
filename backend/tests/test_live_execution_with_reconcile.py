from backend.core.execution_models import (
    ExecutionPlan,
    PlanAction,
    PositionSide,
)
import pytest
import asyncio
from backend.execution.live_execution_system import LiveExecutionSystem


class MockExchange:
    def __init__(self):
        self.position = {"side": "long", "size": 1.0}

    async def open_position(self, symbol, side, quantity):
        self.position = {"side": side.lower(), "size": quantity}

    async def close_position(self, symbol, quantity):
        self.position = {"side": "flat", "size": 0}

    async def get_position(self):
        return self.position


class MockStateStore:
    def get_position(self):
        return {"side": "long", "size": 1.0}


class MockExecutionState:
    def __init__(self):
        self.status = "READY"

    def can_trade(self):
        return True

    def freeze(self):
        self.status = "FROZEN"


@pytest.mark.asyncio
async def test_execute_with_reconciliation():

    exchange = MockExchange()
    state_store = MockStateStore()
    execution_state = MockExecutionState()

    system = LiveExecutionSystem(
        exchange_adapter=exchange,
        sync_engine=None,
        state_store=state_store,
        execution_state=execution_state,
    )

    plan = ExecutionPlan(
        action=PlanAction.OPEN,
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1.0,
        reduce_only=False,
        reason="test",
        source="unit_test",
        timestamp=0,
    )

    await system.execute_plan(plan)

    assert execution_state.status == "READY"
