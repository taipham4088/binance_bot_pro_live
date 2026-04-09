import requests
import inspect

from trading_core.config.engine_config import EngineConfig
from fastapi import APIRouter, Request, HTTPException
from backend.runtime.exchange_config import exchange_config
from backend.runtime.runtime_config import runtime_config
from backend.core.trading_session import canonical_session_id, mode_defers_execution_bootstrap

router = APIRouter()

_ALLOWED_SESSION_MODES = frozenset(
    {"live", "live_shadow", "shadow", "paper", "backtest"}
)


def _default_mode_from_runtime() -> str:
    d = runtime_config.get("mode") or "paper"
    if not isinstance(d, str):
        return "paper"
    d = d.strip().lower().replace("-", "_")
    if d not in _ALLOWED_SESSION_MODES:
        return "paper"
    return d


def _resolve_create_mode(requested: str | None) -> str:
    """
    Explicit ?mode= wins so live + live_shadow can run in parallel.
    If omitted, default from runtime_config (control panel) only.
    """
    if requested is not None:
        m = str(requested).strip().lower().replace("-", "_")
        if m not in _ALLOWED_SESSION_MODES:
            raise HTTPException(status_code=400, detail=f"Invalid session mode: {requested!r}")
        return m
    return _default_mode_from_runtime()


# =========================
# SESSION CONTROL API
# =========================

@router.post("/session/create")
def create_session(request: Request, mode: str | None = None):
    manager = request.app.state.manager

    effective_mode = _resolve_create_mode(mode)

    # ✅ default EngineConfig cho app session (aligned with runtime_config)
    cfg = EngineConfig(
        initial_balance=10000,
        risk_per_trade=0.01,
        symbol=runtime_config.get("symbol") or "BTCUSDT",
        exchange=runtime_config.get("exchange") or "binance",
    )

    sid = canonical_session_id(effective_mode)
    defer = mode_defers_execution_bootstrap(effective_mode)

    session = manager.create_session(
        mode=effective_mode,
        config=cfg,
        app=request.app,
        session_id=sid,
        defer_execution=defer,
    )

    return {
        "session_id": session.id,
        "status": session.status,
        "mode": session.mode,
    }


@router.post("/session/start/{session_id}")
async def start_session(request: Request, session_id: str):
    manager = request.app.state.manager
    if not manager.get(session_id):
        raise HTTPException(
            status_code=404,
            detail=f"Session not found: {session_id!r} — create it first via POST /session/create",
        )

    session = manager.start_session(session_id)

    # 🔥 SET STATUS NGAY LẬP TỨC
    session.status = "RUNNING"

    # 🔥 START LIVE SERVICE ONLY FOR LIVE MODE
    if session.mode == "live":
        from backend.services.live_service import LiveService
        service = LiveService()
        service.start(
            session,
            symbol=runtime_config.get("symbol", "BTCUSDT"),
            timeframe="5m",
        )

    return {
        "session_id": session.id,
        "status": session.status
    }
    

@router.post("/session/stop/{session_id}")
async def stop_session(request: Request, session_id: str):
    manager = request.app.state.manager
    try:
        session = manager.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id!r}")

        print(f"[SESSION] stopping {session_id}")

        print("[EXECUTION] stopping pipeline")

        # stop strategy/signal loop runner first
        runner = getattr(session, "runner", None)
        if runner:
            try:
                runner.stop()
                if runner.is_alive():
                    runner.join(timeout=8)
                print("[EXECUTION] signal loop stopped")
            except Exception as e:
                print("[EXECUTION] signal loop stop error:", e)

        # stop websocket/feed
        market = getattr(session, "market", None) or getattr(session, "data_feed", None)
        if market and hasattr(market, "stop"):
            try:
                market.stop()
            except Exception as e:
                print("[EXECUTION] market stop error:", e)

        # stop health loop + task
        health_loop = getattr(session, "health_loop", None)
        if health_loop:
            try:
                health_loop.stop()
            except Exception:
                pass
        health_task = getattr(session, "health_task", None)
        if health_task:
            try:
                health_task.cancel()
            except Exception:
                pass

        # stop execution system deterministically (await if coroutine)
        live_system = getattr(session, "live_system", None)
        if live_system and hasattr(live_system, "stop"):
            try:
                ret = live_system.stop()
                if inspect.isawaitable(ret):
                    await ret
                print("[EXECUTION] decision loop stopped")
            except Exception as e:
                print("[EXECUTION] live_system stop error:", e)

        engine = getattr(session, "engine", None)
        if engine and engine is not live_system and hasattr(engine, "stop"):
            try:
                ret = engine.stop()
                if inspect.isawaitable(ret):
                    await ret
            except Exception as e:
                print("[EXECUTION] engine stop error:", e)

        session = manager.stop_session(session_id)

        # Ensure heartbeat loop is halted for true STOP state.
        try:
            if getattr(session, "system_state", None):
                session.system_state.stop()
        except Exception:
            pass

        runner_alive = bool(
            getattr(session, "runner", None) and session.runner.is_alive()
        )
        ws_running = bool(
            getattr(getattr(session, "market", None), "client", None)
            and getattr(session.market.client, "running", False)
        )

        print("[EXECUTION] execution pipeline stopped")
        print(f"[SESSION] stopped {session_id}")

        return {
            "session_id": session.id,
            "status": session.status,
            "runner_alive": runner_alive,
            "ws_running": ws_running,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions")
def list_sessions(request: Request):
    manager = request.app.state.manager
    return manager.snapshot()


@router.get("/market")
async def get_market(request: Request):

    manager = request.app.state.manager

    sessions = manager.sessions

    if not sessions:
        symbol = runtime_config.get("symbol", "BTCUSDT")
    else:
        session = list(sessions.values())[0]
        symbol = getattr(session, "symbol", "BTCUSDT")

    # ticker 24h
    ticker = requests.get(
        f"{exchange_config.rest_url}/fapi/v1/ticker/24hr?symbol={symbol}"
    ).json()

    # funding
    premium = requests.get(
        f"{exchange_config.rest_url}/fapi/v1/premiumIndex?symbol={symbol}"
    ).json()

    return {
        "symbol": symbol,
        "price": float(ticker["lastPrice"]),
        "change_24h": float(ticker["priceChangePercent"]),
        "funding": float(premium["lastFundingRate"])
    }