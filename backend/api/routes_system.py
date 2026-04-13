import requests
import inspect
import threading

from trading_core.config.engine_config import EngineConfig
from fastapi import APIRouter, Request, HTTPException
from backend.runtime.exchange_config import exchange_config
from backend.runtime.runtime_config import runtime_config
from backend.runtime.session_config_store import (
    apply_stored_to_trading_session,
    ensure_engine_config,
    load_control_config_merged,
)
from backend.core.trading_session import canonical_session_id, mode_defers_execution_bootstrap
from backend.services.backtest_service import BacktestService

router = APIRouter()
backtest_service = BacktestService()

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
    sid = canonical_session_id(effective_mode)

    # Idempotent create: preserve existing per-session runtime fields (e.g. csv_path).
    existing = manager.get(sid)
    if existing is not None:
        return {
            "session_id": existing.id,
            "status": getattr(existing, "status", "UNKNOWN"),
            "mode": existing.mode,
        }

    stored = load_control_config_merged(sid)
    cfg = EngineConfig(
        initial_balance=float(stored.get("initial_balance") or 10000),
        risk_per_trade=float(stored.get("risk_percent") or 0.01),
        symbol=str(stored.get("symbol") or runtime_config.get("symbol") or "BTCUSDT"),
        exchange=str(stored.get("exchange") or runtime_config.get("exchange") or "binance"),
        mode=effective_mode,
        trade_mode=str(stored.get("trade_mode") or "dual"),
    )
    setattr(cfg, "engine", str(stored.get("strategy") or "range_trend"))

    defer = mode_defers_execution_bootstrap(effective_mode)
    if effective_mode in ("paper", "backtest"):
        defer = True

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
    sess = manager.get(session_id)
    if not sess:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found: {session_id!r} — create it first via POST /session/create",
        )

    ensure_engine_config(sess)
    apply_stored_to_trading_session(sess, load_control_config_merged(session_id))

    if sess.mode == "backtest":
        sess.backtest_service = backtest_service
        def _run_backtest():
            try:
                csv = str(getattr(sess, "csv_path", "") or "").strip()
                if not csv:
                    csv = "data/backtest/input/futures_BTCUSDT_5m_FULL.csv"
                print(f"[BACKTEST START] session_id={sess.id}")
                print(f"[BACKTEST START] csv_path={csv}")
                sess.status = "RUNNING"
                backtest_service.run(session=sess, csv_path=csv)
                if sess.status != "STOPPED":
                    sess.status = "FINISHED"
            except Exception as e:
                sess.last_error = str(e)
                sess.status = "ERROR"
                print("[BACKTEST] run failed:", e)

        threading.Thread(
            target=_run_backtest, daemon=True, name=f"backtest-{sess.id}"
        ).start()
        session = sess
        return {
            "session_id": session.id,
            "status": session.status
        }

    session = manager.start_session(session_id)

    # 🔥 SET STATUS NGAY LẬP TỨC
    session.status = "RUNNING"

    # 🔥 START LIVE SERVICE ONLY FOR LIVE MODE
    if session.mode == "live":
        from backend.services.live_service import LiveService
        service = LiveService()
        sym = getattr(session.config, "symbol", None) or runtime_config.get(
            "symbol", "BTCUSDT"
        )
        service.start(session, symbol=str(sym))

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

        # Stop market/WS first — no further adapter push_candle while runner stops.
        market = getattr(session, "market", None) or getattr(session, "data_feed", None)
        if market and hasattr(market, "stop"):
            try:
                market.stop()
            except Exception as e:
                print("[EXECUTION] market stop error:", e)

        runner = getattr(session, "runner", None)
        if runner:
            try:
                runner.stop()
                if runner.is_alive():
                    runner.join(timeout=8)
                print("[EXECUTION] signal loop stopped")
            except Exception as e:
                print("[EXECUTION] signal loop stop error:", e)

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
    sessions_map = {}
    for session_id, session in manager.sessions.items():
        sessions_map[session_id] = {
            "mode": session.mode,
            "status": getattr(session, "status", "UNKNOWN"),
        }
    return {
        "active_session": manager.active_session_id,
        "sessions": sessions_map,
    }


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