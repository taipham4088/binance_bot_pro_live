from trading_core.config.engine_config import EngineConfig
from fastapi import APIRouter, Request, HTTPException
from backend.runtime.exchange_config import exchange_config
router = APIRouter()

# =========================
# SESSION CONTROL API
# =========================

@router.post("/session/create")
def create_session(request: Request, mode: str = "paper"):
    manager = request.app.state.manager

    # ✅ default EngineConfig cho app session
    cfg = EngineConfig(
        initial_balance=10000,
        risk_per_trade=0.01
    )

    session = manager.create_session(
        mode=mode,
        config=cfg,   # 🔥 QUAN TRỌNG: dùng EngineConfig
        app=request.app
    )

    return {
        "session_id": session.id,
        "status": session.status,
        "mode": session.mode
    }


@router.post("/session/start/{session_id}")
async def start_session(request: Request, session_id: str):
    manager = request.app.state.manager
    if not manager.get(session_id):
        manager.create_session("shadow", {}, app)

    session = manager.start_session(session_id)

    # 🔥 SET STATUS NGAY LẬP TỨC
    session.status = "RUNNING"

    # 🔥 START LIVE SERVICE ONLY FOR LIVE MODE
    if session.mode == "live":
        from backend.services.live_service import LiveService
        service = LiveService()
        service.start(session, symbol="BTCUSDT", timeframe="5m")

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

import requests
from fastapi import Request

@router.get("/market")
async def get_market(request: Request):

    manager = request.app.state.manager

    sessions = manager.sessions

    if not sessions:
        symbol = "BTCUSDT"
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