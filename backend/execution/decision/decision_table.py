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
from typing import Dict, Any
from time import time

from backend.execution.types.execution_plan import ExecutionPlan
from backend.execution.decision.decision_types import (
    Authority,
    ExecutionPlanType,
    HealthState,
)


def _now_ms() -> int:
    return int(time() * 1000)


def evaluate_decision(context: Dict[str, Any]) -> ExecutionPlan:
    """
    PURE FUNCTION – EXECUTION DECISION TABLE

    Input context MUST contain:
        - authority: Authority
        - position: { side: long|short|flat, size: number }
        - intent: Intent
        - risk: { breach: bool }
        - health: HealthState
        - kill_switch: bool

    Output:
        ExecutionPlan(plan, reason, source, timestamp)

    RULES:
        - No side-effect
        - No state mutation
        - No adapter call
        - Deterministic
    """

    authority: Authority = Authority(context["authority"])
    position: Dict[str, Any] = context["position"]
    intent = context["intent"]
    risk: Dict[str, Any] = context["risk"]
    health: HealthState = HealthState(context["health"])
    kill_switch: bool = context["kill_switch"]

    now = _now_ms()
    source = intent.source

    # ------------------------------------------------------------------
    # A. AUTHORITY GATE (ƯU TIÊN CAO NHẤT)
    # ------------------------------------------------------------------
    if authority == Authority.LIVE_READONLY:
        return ExecutionPlan(
            plan=ExecutionPlanType.BLOCK,
            reason="authority=live-readonly",
            source=source,
            timestamp=now,
        )

    # paper và live-trade được đi tiếp

    # ------------------------------------------------------------------
    # B. KILL SWITCH
    # ------------------------------------------------------------------
    if kill_switch:
        return ExecutionPlan(
            plan=ExecutionPlanType.BLOCK,
            reason="kill-switch=on",
            source=source,
            timestamp=now,
        )

    # ------------------------------------------------------------------
    # C. RISK GUARD
    # ------------------------------------------------------------------
    if risk.get("breach") is True:
        # Theo spec: BLOCK hoặc CLOSE tuỳ policy
        # Phase 2: CHỐT là BLOCK, chưa auto-close
        return ExecutionPlan(
            plan=ExecutionPlanType.BLOCK,
            reason="risk=breach",
            source=source,
            timestamp=now,
        )

    # ------------------------------------------------------------------
    # D. SYSTEM HEALTH OVERRIDE
    # ------------------------------------------------------------------
    if health == HealthState.CRITICAL:
        return ExecutionPlan(
            plan=ExecutionPlanType.BLOCK,
            reason="health=critical",
            source=source,
            timestamp=now,
        )

    # degraded: cho phép reduce/close, cấm open
    if health == HealthState.DEGRADED:
        if intent.type in ("open_long", "open_short"):
            return ExecutionPlan(
                plan=ExecutionPlanType.BLOCK,
                reason="health=degraded (no open allowed)",
                source=source,
                timestamp=now,
            )

    # ------------------------------------------------------------------
    # E. POSITION vs INTENT (CORE DECISION)
    # ------------------------------------------------------------------
    side = position.get("side", "flat")

    # ----- CLOSE / REDUCE -----
    if intent.type == "close":
        return ExecutionPlan(
            plan=ExecutionPlanType.CLOSE_POSITION,
            reason="intent=close",
            source=source,
            timestamp=now,
        )

    if intent.type == "reduce":
        return ExecutionPlan(
            plan=ExecutionPlanType.REDUCE_ONLY,
            reason="intent=reduce",
            source=source,
            timestamp=now,
        )

    # ----- OPEN LOGIC -----
    if side == "flat":
        if intent.type == "open_long":
            return ExecutionPlan(
                plan=ExecutionPlanType.OPEN_POSITION,
                reason="flat -> open_long",
                source=source,
                timestamp=now,
            )
        if intent.type == "open_short":
            return ExecutionPlan(
                plan=ExecutionPlanType.OPEN_POSITION,
                reason="flat -> open_short",
                source=source,
                timestamp=now,
            )

    if side == "long":
        if intent.type == "open_long":
            return ExecutionPlan(
                plan=ExecutionPlanType.NOOP,
                reason="already long",
                source=source,
                timestamp=now,
            )
        if intent.type == "open_short":
            return ExecutionPlan(
                plan=ExecutionPlanType.CLOSE_POSITION,
                reason="long -> close before short",
                source=source,
                timestamp=now,
            )

    if side == "short":
        if intent.type == "open_short":
            return ExecutionPlan(
                plan=ExecutionPlanType.NOOP,
                reason="already short",
                source=source,
                timestamp=now,
            )
        if intent.type == "open_long":
            return ExecutionPlan(
                plan=ExecutionPlanType.CLOSE_POSITION,
                reason="short -> close before long",
                source=source,
                timestamp=now,
            )

    # ------------------------------------------------------------------
    # FALLBACK (KHÔNG ĐƯỢC XẢY RA)
    # ------------------------------------------------------------------
    return ExecutionPlan(
        plan=ExecutionPlanType.NOOP,
        reason="no matching rule",
        source=source,
        timestamp=now,
    )
