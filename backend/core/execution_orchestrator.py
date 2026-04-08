# backend/core/execution_orchestrator.py
from backend.core.execution_models import (
    ExecutionPlan as NewExecutionPlan,
    ExecutionDecision as NewExecutionDecision,
    PlanAction,
    PositionSide as ModelPositionSide
)
from enum import Enum
from dataclasses import dataclass
from typing import Optional
import time
from backend.observability.execution_monitor_instance import execution_monitor


# ===== ENUMS =====

class Authority(str, Enum):
    PAPER = "paper"
    LIVE_READONLY = "live-readonly"
    LIVE_TRADE = "live-trade"


class ExecutionPlan(str, Enum):
    NOOP = "NOOP"
    OPEN_POSITION = "OPEN_POSITION"
    REDUCE_ONLY = "REDUCE_ONLY"
    CLOSE_POSITION = "CLOSE_POSITION"
    BLOCK = "BLOCK"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class SystemHealth(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    CRITICAL = "critical"


# ===== DATA MODELS =====

@dataclass
class PositionState:
    side: PositionSide
    size: float


@dataclass
class RiskState:
    breach: bool
    kill_switch: bool


@dataclass
class ExecutionIntent:
    action: str
    symbol: Optional[str] = None
    size: Optional[float] = None
    price: Optional[float] = None
    source: str = "strategy"

@dataclass
class ExecutionDecision:
    plan: ExecutionPlan
    reason: str
    source: str
    timestamp: int


# ===== ORCHESTRATOR =====

class ExecutionOrchestrator:
    """
    CORE BRAIN – tuân theo Section 8, 9, 11, 13
    Không gọi exchange
    Không mutate state
    """

    def evaluate(
        self,
        *,
        authority: Authority,
        position: PositionState,
        risk: RiskState,
        health: SystemHealth,
        intent: ExecutionIntent,
    ) -> ExecutionDecision:

        now = int(time.time() * 1000)
        # ===== Execution Monitoring: signal trace =====
        try:
            if intent.symbol:

                signal_price = getattr(intent, "price", None)

                if signal_price is None and hasattr(intent, "metadata"):
                    signal_price = intent.metadata.get("price")

                # fallback lấy giá market
                if signal_price is None:
                    try:
                        from backend.live.market.live_feature_engine import live_feature_engine
                        signal_price = live_feature_engine.last_price
                        print("MARKET PRICE FALLBACK:", signal_price)
                    except Exception as e:
                        print("MARKET PRICE ERROR:", e)
                        signal_price = None

                print("DEBUG INTENT:", intent)
                print("DEBUG SIGNAL PRICE:", signal_price)

                execution_monitor.start_trace(
                    symbol=intent.symbol,
                    side=getattr(intent, "action", "unknown"),
                    size=float(intent.size or 0),
                    signal_price=signal_price
                )

        except Exception:
            pass

        # ---- A. Authority gate (Section 9.2.A) ----
        if authority == Authority.LIVE_READONLY:
            return self._build_plan(
                PlanAction.BLOCK,
                position,
                intent,
                now,
                reason="authority=live-readonly",
            )

        # ---- B. Kill switch (Section 9.2.B) ----
        if risk.kill_switch:
            return self._build_plan(
                PlanAction.BLOCK,
                position,
                intent,
                now,
                reason="kill-switch=ON"
            )

        # ---- C. Risk breach (Section 9.2.C) ----
        if risk.breach:
            return self._build_plan(
                PlanAction.BLOCK,
                position,
                intent,
                now,
                reason="risk-breach"
            )

        # ---- D. System health override (Section 9.2.E) ----
        if health == SystemHealth.CRITICAL:
            return self._build_plan(
                PlanAction.BLOCK,
                position,
                intent,
                now,
                reason="system-health=critical"
            )

        action = getattr(intent, "action", "")

        if health == SystemHealth.DEGRADED and action.startswith("open"):
            return self._build_plan(
                PlanAction.BLOCK,
                position,
                intent,
                now,
                reason="system-health=degraded"
            )

        # ---- E. Position vs Intent (Section 9.2.D) ----
        return self._decide_by_position(position, intent, now)

    # ===== INTERNAL =====

    def _decide_by_position(
        self,
        position: PositionState,
        intent: ExecutionIntent,
        ts: int,
    ) -> ExecutionDecision:
        
        if position is None:
            position = PositionState(side=PositionSide.FLAT, size=0)

        side = position.side
        action = intent.action

        # =========================
        # FLAT
        # =========================
        if side == PositionSide.FLAT:
            if action == "open_long":
                return self._build_plan(
                    PlanAction.OPEN,
                    position,
                    intent,
                    ts,
                    reason="open long from flat",
                )

            if action == "open_short":
                return self._build_plan(
                    PlanAction.OPEN,
                    position,
                    intent,
                    ts,
                    reason="open short from flat",
                )

            return self._build_plan(
                PlanAction.NOOP,
                position,
                intent,
                ts,
                reason="flat + non-open intent",
            )

        # =========================
        # LONG
        # =========================
        if side == PositionSide.LONG:

            # ===== CLOSE luôn được ưu tiên =====
            if action == "close":
                return self._build_plan(
                    PlanAction.CLOSE,
                    position,
                    intent,
                    ts,
                    reason="close long",
                    reduce_only=True,
                )

            # ===== REDUCE =====
            if action == "reduce":
                return self._build_plan(
                    PlanAction.REDUCE,
                    position,
                    intent,
                    ts,
                    reason="reduce long",
                    reduce_only=True,
                )

            # ===== REVERSE =====
            if action == "open_short":
                return self._build_plan(
                    PlanAction.CLOSE,
                    position,
                    intent,
                    ts,
                    reason="long -> short (step 1/2)",
                    reduce_only=True,
                )

            # ===== SAME SIDE =====
            if action == "open_long":
                return self._build_plan(
                    PlanAction.NOOP,
                    position,
                    intent,
                    ts,
                    reason="already long",
                )

        # =========================
        # SHORT
        # =========================
        if side == PositionSide.SHORT:

            if action == "close":
                return self._build_plan(
                    PlanAction.CLOSE,
                    position,
                    intent,
                    ts,
                    reason="close short",
                    reduce_only=True,
                )

            if action == "reduce":
                return self._build_plan(
                    PlanAction.REDUCE,
                    position,
                    intent,
                    ts,
                    reason="reduce short",
                    reduce_only=True,
                )

            if action == "open_long":
                return self._build_plan(
                    PlanAction.CLOSE,
                    position,
                    intent,
                    ts,
                    reason="short -> long (step 1/2)",
                    reduce_only=True,
                )

            if action == "open_short":
                return self._build_plan(
                    PlanAction.NOOP,
                    position,
                    intent,
                    ts,
                    reason="already short",
                )

        # =========================
        # INVALID STATE
        # =========================
        return self._build_plan(
            PlanAction.BLOCK,
            position,
            intent,
            ts,
            reason="invalid-state",
        )
   
    # ===== NEW DECISION BUILDER =====
   
    def _build_plan(
        self,
        action: PlanAction,
        position: PositionState,
        intent: ExecutionIntent,
        ts: int,
        reason: str,
        reduce_only: bool = False,
    ) -> NewExecutionDecision:

        # Xác định side từ intent
        side = None
        size = float(intent.size or 0)

        if intent.action == "open_long":
            side = ModelPositionSide.LONG

        elif intent.action == "open_short":
            side = ModelPositionSide.SHORT

        # close / reduce sẽ không cần side
        # vì execution layer sẽ dùng position hiện tại

        plan = NewExecutionPlan(
            action=action,
            symbol=intent.symbol,
            side=side,
            quantity=size,
            reduce_only=reduce_only,
            reason=reason,
            source=intent.source,
            timestamp=ts,
        )
        object.__setattr__(
            plan,
            "metadata",
            getattr(intent, "metadata", {}),
        )
        return NewExecutionDecision(plan=plan)

    
