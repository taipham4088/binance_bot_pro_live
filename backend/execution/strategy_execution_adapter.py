"""
Session-scoped bridge: DualEngine (sync bar loop) → TradingSession.inject_intent →
execution.orchestrator.ExecutionOrchestrator.

Holds only references to the owning TradingSession and an event loop; no globals.
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from typing import TYPE_CHECKING, Any, Callable, Optional

from trading_core.execution_policy.intent_schema import ExecutionIntent, IntentType

if TYPE_CHECKING:
    from backend.core.trading_session import TradingSession

logger = logging.getLogger(__name__)


def _session_symbol(session: TradingSession) -> str:
    cfg = session.config
    if isinstance(cfg, dict):
        s = cfg.get("symbol") or "BTCUSDT"
    else:
        s = getattr(cfg, "symbol", None) or "BTCUSDT"
    return str(s).strip().upper() or "BTCUSDT"


def _qty_from_risk(session: TradingSession, order_intent: dict) -> float:
    """
    Dashboard-controlled sizing: risk_money = equity * risk_per_trade (session config),
    then qty = risk_money / stop_distance (USDT-M style: dollars at risk per unit price move).
    """
    entry = float(order_intent.get("entry") or 0)
    sl = float(order_intent.get("sl") or 0)
    stop_distance = abs(entry - sl)
    if stop_distance < 1e-12:
        raise ValueError("strategy order_intent: need entry/sl with non-zero distance")
    if not math.isfinite(entry) or not math.isfinite(sl):
        raise ValueError("strategy order_intent: entry/sl must be finite")

    rc = session.get_risk_config()
    risk_percent = float(rc.get("risk_per_trade", 0.01))
    if not math.isfinite(risk_percent) or risk_percent <= 0:
        raise ValueError("session risk_per_trade must be a positive finite number")

    sa = getattr(session, "strategy_account", None)
    if sa is None or not hasattr(sa, "get_equity"):
        raise RuntimeError("session.strategy_account with get_equity() is required for sizing")
    equity = float(sa.get_equity())
    if not math.isfinite(equity) or equity < 0:
        raise ValueError("strategy account equity must be a non-negative finite number")

    risk_money = equity * risk_percent
    if not math.isfinite(risk_money) or risk_money <= 0:
        raise ValueError("computed risk_money must be positive")

    qty = risk_money / stop_distance
    if not math.isfinite(qty):
        raise ValueError("computed qty is not finite")
    qty = max(qty, 0.0)
    qty = round(qty, 6)
    if qty <= 0:
        raise ValueError("computed qty must be positive after rounding")
    return qty


class StrategyExecutionAdapter:
    """
    Bridges DualEngine.send_order to the session execution pipeline.

    ``send_order`` may be invoked from a worker thread (e.g. LiveRunner); the adapter
    schedules ``inject_intent`` on the provided asyncio loop and blocks for the result.
    Do not call ``send_order`` from a coroutine running on the same loop (deadlock).
    """

    def __init__(
        self,
        session: TradingSession,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        intent_id_factory: Optional[Callable[[], str]] = None,
        submit_timeout_s: float = 120.0,
    ):
        self._session = session
        self._loop = loop
        self._intent_id_factory = intent_id_factory or (lambda: str(uuid.uuid4()))
        self._submit_timeout_s = submit_timeout_s

    def send_order(self, order_intent: dict) -> Any:
        symbol = _session_symbol(self._session)
        side = str(order_intent.get("side") or "").upper()
        if side not in ("LONG", "SHORT"):
            raise ValueError("order_intent.side must be LONG or SHORT")

        qty = _qty_from_risk(self._session, order_intent)

        intent = ExecutionIntent(
            intent_id=self._intent_id_factory(),
            symbol=symbol,
            type=IntentType.SET_POSITION,
            side=side,
            qty=qty,
            source="dual_engine",
            metadata={
                "entry": order_intent.get("entry"),
                "sl": order_intent.get("sl"),
                "tp": order_intent.get("tp"),
                "risk": order_intent.get("risk"),
                "meta": order_intent.get("meta"),
            },
        )
        intent.validate_schema()

        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError as e:
                raise RuntimeError(
                    "StrategyExecutionAdapter requires an asyncio event loop "
                    "(pass loop= from the app when constructing the adapter)."
                ) from e

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None and running is loop:
            raise RuntimeError(
                "StrategyExecutionAdapter.send_order() must not run inside a task on "
                "the same loop it uses; run the strategy bar loop on a worker thread."
            )

        async def _run():
            async with self._session.execution_lock:
                return await self._session.inject_intent(intent)

        fut = asyncio.run_coroutine_threadsafe(_run(), loop)
        try:
            return fut.result(timeout=self._submit_timeout_s)
        except Exception:
            logger.exception(
                "strategy execution failed session_id=%s symbol=%s",
                getattr(self._session, "id", "?"),
                symbol,
            )
            raise
