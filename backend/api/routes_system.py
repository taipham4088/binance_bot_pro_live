import requests

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
def stop_session(request: Request, session_id: str):
    manager = request.app.state.manager
    try:
        session = manager.stop_session(session_id)
        return {
            "session_id": session.id,
            "status": session.status
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