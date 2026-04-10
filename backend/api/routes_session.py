import threading

from fastapi import APIRouter, Request, HTTPException, Body
from pydantic import BaseModel

from trading_core.config.engine_config import EngineConfig

from backend.runtime.runtime_config import runtime_config
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


def _ensure_engine_config(session) -> None:
    """Paper/Backtest services need EngineConfig-style attributes (not a plain dict)."""
    if isinstance(session.config, EngineConfig):
        return
    if not isinstance(session.config, dict):
        session.config = EngineConfig(
            initial_balance=10000.0,
            risk_per_trade=float(runtime_config.get("risk_percent", 0.01) or 0.01),
            symbol=str(runtime_config.get("symbol") or "BTCUSDT"),
            exchange=str(runtime_config.get("exchange") or "binance"),
            mode=str(getattr(session, "mode", None) or "paper"),
            trade_mode=str(runtime_config.get("trade_mode") or "dual"),
        )
        return
    d = session.config
    session.config = EngineConfig(
        initial_balance=float(d.get("initial_balance", 10000)),
        risk_per_trade=float(
            d.get("risk_per_trade", runtime_config.get("risk_percent", 0.01) or 0.01)
        ),
        symbol=str(d.get("symbol") or runtime_config.get("symbol") or "BTCUSDT"),
        exchange=str(d.get("exchange") or runtime_config.get("exchange") or "binance"),
        mode=str(d.get("mode") or getattr(session, "mode", None) or "paper"),
        trade_mode=str(d.get("trade_mode") or runtime_config.get("trade_mode") or "dual"),
    )


def _set_session_initial_balance(session, value: float) -> None:
    c = session.config
    if isinstance(c, dict):
        c["initial_balance"] = float(value)
    else:
        setattr(c, "initial_balance", float(value))


def _resolve_session_for_config(manager):
    """Active session, else session matching control-panel mode, else any session."""
    session = manager.get_active()
    if session:
        return session
    mode_raw = runtime_config.get("mode")
    if mode_raw:
        sid = canonical_session_id(str(mode_raw).strip().lower().replace("-", "_"))
        session = manager.get(sid)
        if session:
            return session
    if manager.sessions:
        return next(iter(manager.sessions.values()))
    return None


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

    session = manager.create_session(
        mode=effective_mode,
        config={
            "symbol": sym,
            "engine": payload.engine,
            "risk_per_trade": runtime_config.get("risk_percent", 0.01),
        },
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


@router.post("/config")
async def update_session_config(req: Request, payload: dict = Body(...)):
    manager = req.app.state.manager
    session = _resolve_session_for_config(manager)

    if not session:
        return {"status": "no session"}

    print("[CONTROL PANEL APPLY]")
    print("payload =", payload)
    print("session =", session.id)
    print("config_before =", session.config)

    if "initial_balance" in payload:
        try:
            _set_session_initial_balance(session, float(payload["initial_balance"]))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="initial_balance must be a number")

    print("[CONTROL PANEL UPDATED]")
    print("config_after =", session.config)
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
