from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from backend.runtime.runtime_config import runtime_config
from backend.core.trading_session import canonical_session_id, mode_defers_execution_bootstrap

router = APIRouter()

_ALLOWED_SESSION_MODES = frozenset(
    {"live", "live_shadow", "shadow", "paper", "backtest"}
)


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

    rt_sym = runtime_config.get("symbol")
    sym = payload.symbol or rt_sym
    if payload.symbol and rt_sym and payload.symbol != rt_sym:
        print(
            f"WARNING: session/create symbol {payload.symbol!r} overrides "
            f"runtime_config {rt_sym!r}"
        )

    sid = canonical_session_id(effective_mode)

    session = manager.create_session(
        mode=effective_mode,
        config={
            "symbol": sym,
            "engine": payload.engine,
        },
        app=req.app,
        session_id=sid,
        defer_execution=mode_defers_execution_bootstrap(effective_mode),
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
