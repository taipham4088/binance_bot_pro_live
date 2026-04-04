# backend/tests/test_execution_core.py

from backend.core.execution_models import ExecutionPlan as CoreExecutionPlan
from backend.core.execution_models import PlanAction
from backend.core.execution_models import PositionSide as CorePositionSide

import pytest
import time

from backend.core.execution_orchestrator import (
    ExecutionOrchestrator,
    Authority,
    PositionSide,
    SystemHealth,
    PositionState,
    RiskState,
    ExecutionIntent,
)

from backend.core.execution_timeline import (
    ExecutionTimeline,
    ExecutionState,
    make_initial_state,
    LastDecision,
)


# =========================
# ORCHESTRATOR TESTS
# =========================

def test_live_readonly_blocks():
    orch = ExecutionOrchestrator()

    decision = orch.evaluate(
        authority=Authority.LIVE_READONLY,
        position=PositionState(side=PositionSide.FLAT, size=0),
        risk=RiskState(breach=False, kill_switch=False),
        health=SystemHealth.NORMAL,
        intent=ExecutionIntent(action="open_long"),
    )

    assert decision.plan.action == PlanAction.BLOCK
    assert "readonly" in decision.plan.reason


def test_kill_switch_blocks():
    orch = ExecutionOrchestrator()

    decision = orch.evaluate(
        authority=Authority.LIVE_TRADE,
        position=PositionState(side=PositionSide.FLAT, size=0),
        risk=RiskState(breach=False, kill_switch=True),
        health=SystemHealth.NORMAL,
        intent=ExecutionIntent(action="open_long"),
    )

    assert decision.plan.action == PlanAction.BLOCK
    assert "kill-switch" in decision.plan.reason


def test_flat_open_long():
    orch = ExecutionOrchestrator()

    decision = orch.evaluate(
        authority=Authority.LIVE_TRADE,
        position=PositionState(side=PositionSide.FLAT, size=0),
        risk=RiskState(breach=False, kill_switch=False),
        health=SystemHealth.NORMAL,
        intent=ExecutionIntent(action="open_long"),
    )

    assert decision.plan.action == PlanAction.OPEN


def test_long_open_short_does_not_reverse():
    """
    Quan trọng: không reverse trực tiếp
    """
    orch = ExecutionOrchestrator()

    decision = orch.evaluate(
        authority=Authority.LIVE_TRADE,
        position=PositionState(side=PositionSide.LONG, size=1),
        risk=RiskState(breach=False, kill_switch=False),
        health=SystemHealth.NORMAL,
        intent=ExecutionIntent(action="open_short"),
    )

    assert decision.plan.action == PlanAction.CLOSE
    assert "step 1/2" in decision.plan.reason


# =========================
# TIMELINE / STATE MACHINE TESTS
# =========================

def test_idle_to_opening_transition():
    state = make_initial_state(
        session_id="s1",
        mode="live",
        authority="live-trade",
        health="normal",
    )

    timeline = ExecutionTimeline(state)

    now = int(time.time() * 1000)

    decision = LastDecision(
        plan=CoreExecutionPlan(
            action=PlanAction.OPEN,
            symbol="BTCUSDT",
            side=CorePositionSide.LONG,
            quantity=1,
            reduce_only=False,
            reason="test open",
            source="test",
            timestamp=now,
        ),
        reason="test open",
        source="test",
        timestamp=now,
    )

    delta = timeline.step(decision)

    assert delta["type"] == "DELTA"
    assert delta["timeline_index"] == 1

    snapshot = timeline.snapshot()
    assert snapshot["execution_state"] == ExecutionState.OPENING.value


def test_invalid_transition_goes_error():
    """
    IDLE + REDUCE = ERROR
    """
    state = make_initial_state(
        session_id="s2",
        mode="live",
        authority="live-trade",
        health="normal",
    )

    timeline = ExecutionTimeline(state)

    now = int(time.time() * 1000)

    decision = LastDecision(
        plan=CoreExecutionPlan(
            action=PlanAction.REDUCE,
            symbol="BTCUSDT",
            side=CorePositionSide.LONG,
            quantity=1,
            reduce_only=True,
            reason="invalid reduce",
            source="test",
            timestamp=now,
        ),
        reason="invalid reduce",
        source="test",
        timestamp=now,
    )

    timeline.step(decision)
    snapshot = timeline.snapshot()

    assert snapshot["execution_state"] == ExecutionState.ERROR.value


def test_block_transition():
    state = make_initial_state(
        session_id="s3",
        mode="live",
        authority="live-trade",
        health="normal",
    )

    timeline = ExecutionTimeline(state)

    now = int(time.time() * 1000)

    decision = LastDecision(
        plan=CoreExecutionPlan(
            action=PlanAction.BLOCK,
            symbol=None,
            side=CorePositionSide.FLAT,
            quantity=0,
            reduce_only=False,
            reason="manual block",
            source="system",
            timestamp=now,
        ),
        reason="manual block",
        source="system",
        timestamp=now,
    )

    timeline.step(decision)
    snapshot = timeline.snapshot()

    assert snapshot["execution_state"] == ExecutionState.BLOCKED.value
