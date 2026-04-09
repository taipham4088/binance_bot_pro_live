# backend/core/session_runtime.py
from backend.core.execution_orchestrator import ExecutionIntent
from backend.core.execution_orchestrator import ExecutionOrchestrator
from backend.core.execution_timeline import (
    ExecutionTimeline,
    make_initial_state,
    LastDecision,
)
from backend.core.state_hub import StateHub

import math
import time


class SessionRuntime:
    """
    1 session = 1 execution brain + 1 timeline
    """

    def __init__(
        self,
        *,
        session_id: str,
        mode: str,
        authority: str,
        health: str,
        statehub: StateHub,
    ):
        self.session_id = session_id
        self.statehub = statehub
        self.orchestrator = ExecutionOrchestrator()

        initial_state = make_initial_state(
            session_id=session_id,
            mode=mode,
            authority=authority,
            health=health,
        )

        self.timeline = ExecutionTimeline(initial_state)

    # ---------- PUBLIC ----------

    async def start(self):
        """
        Emit SNAPSHOT khi session start
        """
        snapshot = self.timeline.snapshot()
        await self.statehub.emit_snapshot(self.session_id, snapshot)

    def build_execution_intent(self, ws_intent):
        """
        Convert WS Intent → Core ExecutionIntent
        """
        payload = ws_intent.payload or {}

        action_map = {
            "OPEN_LONG": "open_long",
            "OPEN_SHORT": "open_short",
            "CLOSE": "close",
            "REDUCE": "reduce",
        }

        action = action_map.get(ws_intent.type.upper())

        if not action:
            raise ValueError(f"Unsupported intent type: {ws_intent.type}")

        return ExecutionIntent(
            action=action,
            symbol=payload.get("symbol"),
            size=payload.get("size"),
            source=ws_intent.source,
            metadata=payload, 
        )

    async def handle_intent(
        self,
        *,
        authority,
        position,
        risk,
        health,
        intent,
    ):
        """
        Nhận intent → orchestrator → timeline → WS
        """

        decision = self.orchestrator.evaluate(
            authority=authority,
            position=position,
            risk=risk,
            health=health,
            intent=intent,
        )
        print(
            "[DECISION BEFORE EXEC]",
            type(decision),
            getattr(decision.plan, "metadata", None),
        )

        last_decision = LastDecision(
            plan=decision.plan,
            reason=decision.reason,
            source=decision.source,
            timestamp=decision.timestamp,
        )

        delta = self.timeline.step(last_decision)
        await self.statehub.emit_delta(self.session_id, delta)


def _coerce_positive_risk_fraction(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or x <= 0:
        return None
    return x


def sync_dashboard_risk_to_all_sessions(manager) -> None:
    """
    Push runtime_config['risk_percent'] into each host TradingSession's
    risk_config (risk_per_trade). No-op if manager missing or value invalid.
    """
    from backend.runtime.runtime_config import runtime_config

    rp = _coerce_positive_risk_fraction(runtime_config.get("risk_percent"))
    if rp is None or manager is None:
        return
    for session in list(manager.sessions.values()):
        session.set_risk_config({"risk_per_trade": rp})


def _normalize_dashboard_symbol(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip().upper()
    return s if s else None


def sync_dashboard_symbol_to_all_sessions(manager, symbol: str | None = None) -> list:
    """
    Push control-panel symbol to each TradingSession (pending if position open).
    If symbol is None, uses runtime_config['symbol'].
    """
    from backend.runtime.runtime_config import runtime_config

    sym = _normalize_dashboard_symbol(symbol)
    if sym is None:
        sym = _normalize_dashboard_symbol(runtime_config.get("symbol"))
    if not sym or manager is None:
        return []
    out = []
    for sid, session in list(manager.sessions.items()):
        out.append({"session_id": sid, **session.request_symbol_change(sym)})
    return out
