import threading

from fastapi import APIRouter, Request, HTTPException, Body, Query
from pydantic import BaseModel

from trading_core.config.engine_config import EngineConfig

from backend.runtime.runtime_config import runtime_config
from backend.runtime.session_config_store import (
    apply_stored_to_trading_session,
    ensure_engine_config as _ensure_engine_config,
    load_control_config_merged,
    save_control_config_merge,
)
from backend.core.trading_session import canonical_session_id, mode_defers_execution_bootstrap
from backend.services.paper_service import PaperService
from backend.services.backtest_service import BacktestService

router = APIRouter()

paper_service = PaperService()
backtest_service = BacktestService()

_DEFAULT_SESSION_CSV = "data/backtest/input/futures_BTCUSDT_5m_FULL.csv"


def _backtest_csv_path(session) -> str:
    p = getattr(session, "csv_path", None)
    if p and str(p).strip():
        return str(p).strip()
    return _DEFAULT_SESSION_CSV


def _spawn_backtest_thread(session) -> None:
    def run_backtest():
        try:
            csv = _backtest_csv_path(session)
            print(f"[BACKTEST THREAD] session_id={session.id}")
            print(f"[BACKTEST THREAD] csv_path={csv}")
            session.status = "RUNNING"
            backtest_service.run(session=session, csv_path=csv)
            session.status = "FINISHED"
        except Exception as e:
            session.last_error = str(e)
            session.status = "ERROR"
            print("[BACKTEST] run failed:", e)

    threading.Thread(
        target=run_backtest, daemon=True, name=f"backtest-{session.id}"
    ).start()

_ALLOWED_SESSION_MODES = frozenset(
    {"live", "live_shadow", "shadow", "paper", "backtest"}
)

_UI_SESSION_MODES = frozenset({"live", "shadow", "paper", "backtest"})


class CreateSessionRequest(BaseModel):
    mode: str | None = None  # explicit mode; if omitted → runtime_config default only
    symbol: str | None = None
    engine: str | None = None


def _default_mode_from_runtime() -> str:
    d = runtime_config.get("mode") or "shadow"
    if not isinstance(d, str):
        return "shadow"
    d = d.strip().lower().replace("-", "_")
    if d not in _ALLOWED_SESSION_MODES:
        return "shadow"
    return d


def _get_session_for_control(manager, payload: dict):
    sid = _session_id_from_control_payload(payload)
    session = manager.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _set_session_initial_balance(session, value: float) -> None:
    c = session.config
    if isinstance(c, dict):
        c["initial_balance"] = float(value)
    else:
        setattr(c, "initial_balance", float(value))


def _session_id_from_control_payload(payload: dict) -> str:
    mode = payload.get("mode")
    if mode is None or str(mode).strip() == "":
        raise HTTPException(status_code=400, detail="mode is required")
    m = str(mode).strip().lower().replace("-", "_")
    if m not in _UI_SESSION_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode!r}")
    return canonical_session_id(m)


def _resolve_payload_mode(payload: CreateSessionRequest) -> str:
    if payload.mode is not None:
        m = str(payload.mode).strip().lower().replace("-", "_")
        if m not in _ALLOWED_SESSION_MODES:
            raise HTTPException(status_code=400, detail=f"Invalid session mode: {payload.mode!r}")
        return m
    return _default_mode_from_runtime()


@router.post("/session/create")
async def create_session(req: Request, payload: CreateSessionRequest):
    manager = req.app.state.manager

    effective_mode = _resolve_payload_mode(payload)
    sid = canonical_session_id(effective_mode)

    # Idempotent create: keep existing session runtime attrs (csv_path, progress, etc.).
    existing = manager.get(sid)
    if existing is not None:
        return {
            "session_id": existing.id,
            "mode": existing.mode,
        }

    rt_sym = runtime_config.get("symbol")
    sym = payload.symbol or rt_sym
    if payload.symbol and rt_sym and payload.symbol != rt_sym:
        print(
            f"WARNING: session/create symbol {payload.symbol!r} overrides "
            f"runtime_config {rt_sym!r}"
        )

    defer = mode_defers_execution_bootstrap(effective_mode)
    if effective_mode in ("paper", "backtest"):
        defer = True

    stored = load_control_config_merged(sid)
    config = {
        "symbol": sym,
        "engine": payload.engine or stored.get("strategy", "range_trend"),
        "risk_per_trade": float(stored.get("risk_percent", 0.01)),
        "trade_mode": str(stored.get("trade_mode", "dual")),
        "initial_balance": float(stored.get("initial_balance", 10000)),
    }
    print("[SESSION CREATE CONFIG]")
    print("mode =", effective_mode)
    print("trade_mode =", config.get("trade_mode"))
    print("risk =", config.get("risk_per_trade"))
    print("strategy =", config.get("engine"))
    print("balance =", config.get("initial_balance"))

    session = manager.create_session(
        mode=effective_mode,
        config=config,
        app=req.app,
        session_id=sid,
        defer_execution=defer,
    )

    return {
        "session_id": session.id,
        "mode": effective_mode,
    }


@router.get("/session/list")
async def list_sessions(req: Request):
    manager = req.app.state.manager

    result = {}

    for session_id, session in manager.sessions.items():
        result[session_id] = {
            "id": session.id,
            "mode": session.mode,
            "status": getattr(session, "status", "idle"),
            "config": session.config,
        }

    return result


def _public_control_config_from_stored(stored: dict) -> dict:
    return {
        "trade_mode": str(stored.get("trade_mode") or "dual"),
        "risk_percent": float(stored.get("risk_percent") or 0.01),
        "initial_balance": float(stored.get("initial_balance") or 10000),
        "strategy": str(stored.get("strategy") or "range_trend"),
        "symbol": str(stored.get("symbol") or "BTCUSDT"),
        "exchange": str(stored.get("exchange") or "binance"),
    }


def _public_control_config_from_session(session) -> dict:
    """Control-panel fields for dashboard; supports dict or EngineConfig on session.config."""
    c = session.config
    if isinstance(c, dict):
        return {
            "trade_mode": str(c.get("trade_mode") or "dual"),
            "risk_percent": float(
                c.get("risk_per_trade", c.get("risk_percent", 0.01)) or 0.01
            ),
            "initial_balance": float(c.get("initial_balance", 10000) or 10000),
            "strategy": str(c.get("engine") or c.get("strategy") or "range_trend"),
        }
    _ensure_engine_config(session)
    c = session.config
    strategy = getattr(c, "engine", None) or getattr(c, "strategy", None) or "range_trend"
    return {
        "trade_mode": str(getattr(c, "trade_mode", None) or "dual"),
        "risk_percent": float(getattr(c, "risk_per_trade", 0.01) or 0.01),
        "initial_balance": float(getattr(c, "initial_balance", 10000) or 10000),
        "strategy": str(strategy),
    }


@router.get("/config")
async def get_session_config(req: Request, session: str = Query(..., description="Session id, e.g. live, backtest")):
    sid = canonical_session_id(session)
    stored = load_control_config_merged(sid)
    return _public_control_config_from_stored(stored)


@router.post("/config")
async def update_session_config(
    req: Request,
    session: str = Query(..., description="Target session id, e.g. live, backtest"),
    payload: dict = Body(...),
):
    manager = req.app.state.manager
    sid = canonical_session_id(session)
    sess = manager.get(sid)

    updates = {}
    if "initial_balance" in payload:
        updates["initial_balance"] = payload["initial_balance"]
    if "trade_mode" in payload:
        updates["trade_mode"] = payload["trade_mode"]
    if "risk_percent" in payload:
        updates["risk_percent"] = payload["risk_percent"]
    if "strategy" in payload:
        updates["strategy"] = payload["strategy"]

    merged = save_control_config_merge(sid, updates)

    print("[CONTROL PANEL APPLY]")
    print("payload =", payload)
    print("session_id =", sid)
    if sess:
        print("config_before =", sess.config)

    if sess:
        _ensure_engine_config(sess)
        apply_stored_to_trading_session(sess, merged)

    print("[CONTROL PANEL UPDATED]")
    if sess:
        print("config_after =", sess.config)
    return {"status": "updated"}


@router.post("/import")
async def import_backtest_csv(req: Request, payload: dict = Body(...)):
    manager = req.app.state.manager
    mode = payload.get("mode")
    path = payload.get("path")
    if mode is None or path is None or str(path).strip() == "":
        raise HTTPException(
            status_code=400, detail="mode and non-empty path are required"
        )
    sid = canonical_session_id(str(mode).strip().lower().replace("-", "_"))
    session = manager.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.csv_path = str(path).strip()
    print(f"[BACKTEST IMPORT] session_id={session.id}")
    print(f"[BACKTEST IMPORT] csv_path={session.csv_path}")
    return {"status": "imported", "path": session.csv_path}


@router.post("/export")
async def session_export(req: Request, payload: dict = Body(...)):
    manager = req.app.state.manager
    session = _get_session_for_control(manager, payload)

    if session.mode == "backtest":
        try:
            path = backtest_service.export(session)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"status": "exported", "file": path}

    raise HTTPException(
        status_code=400,
        detail="Session export for this mode is not supported via this endpoint",
    )


@router.post("/start")
async def session_control_start(req: Request, payload: dict = Body(...)):
    manager = req.app.state.manager
    session = _get_session_for_control(manager, payload)
    _ensure_engine_config(session)
    stored = load_control_config_merged(session.id)
    apply_stored_to_trading_session(session, stored)
    print("[SESSION CONFIG]")
    print(session.config)
    print("[SESSION START CONFIG]")
    print(session.config)

    if session.mode == "paper":
        paper_service.start(session=session, csv_path=_DEFAULT_SESSION_CSV)
        session.status = "RUNNING"
    elif session.mode == "live":
        print("[LIVE START CONFIG]")
        print("trade_mode =", getattr(session.config, "trade_mode", None))
        session.start()
    elif session.mode == "backtest":
        print(f"[BACKTEST START] session_id={session.id}")
        print(f"[BACKTEST START] csv_path={getattr(session, 'csv_path', None)}")
        print("[BACKTEST START CONFIG]")
        print("trade_mode =", getattr(session.config, "trade_mode", None))
        session.status = "RUNNING"
        _spawn_backtest_thread(session)
    else:
        session.start()

    return {"status": session.status, "mode": session.mode}


@router.post("/stop")
async def session_control_stop(req: Request, payload: dict = Body(...)):
    manager = req.app.state.manager
    session = _get_session_for_control(manager, payload)

    if session.mode == "paper":
        paper_service.stop(session)
    else:
        session.stop()

    session.status = "STOPPED"
    return {"status": "stopped", "mode": session.mode, "session_status": session.status}


@router.post("/restart")
async def session_control_restart(req: Request, payload: dict = Body(...)):
    manager = req.app.state.manager
    session = _get_session_for_control(manager, payload)
    _ensure_engine_config(session)
    stored = load_control_config_merged(session.id)
    apply_stored_to_trading_session(session, stored)

    if session.mode == "paper":
        paper_service.stop(session)
        paper_service.start(session=session, csv_path=_DEFAULT_SESSION_CSV)
        session.status = "RUNNING"
    elif session.mode == "backtest":
        session.status = "RUNNING"
        _spawn_backtest_thread(session)
    else:
        session.stop()
        session.start()
        session.status = "RUNNING"

    return {"status": "restarted", "mode": session.mode, "session_status": session.status}
