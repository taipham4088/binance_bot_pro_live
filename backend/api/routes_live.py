from fastapi import APIRouter, Request, Body

from backend.core.trading_session import TradingSession
from backend.services.paper_service import PaperService
from backend.services.live_service import LiveService

from trading_core.config.engine_config import EngineConfig


router = APIRouter()

paper = PaperService()
live = LiveService()


# =========================
# PAPER
# =========================

@router.post("/paper/start")
def start_paper(req: dict, request: Request):

    manager = request.app.state.manager

    cfg = EngineConfig(**req["config"])

    session = manager.create_session(
        mode="paper",
        config=cfg,
        app=request.app
    )

    session_id = paper.start(
        session,
        csv_path=req["csv_path"],
        speed=req.get("speed", 0.2)
    )

    return {
        "session_id": session_id,
        "status": "RUNNING"
    }


@router.post("/paper/stop/{session_id}")
def stop_paper(session_id: str, request: Request):

    manager = request.app.state.manager
    session = manager.get(session_id)

    if not session:
        return {"error": "session not found"}

    paper.stop(session)

    return {"status": "STOPPING"}


# =========================
# LIVE (OBSERVE ONLY)
# =========================

@router.post("/start")
def start_live(request: Request, req: dict = Body(...)):

    manager = request.app.state.manager

    session_id = req["session_id"]
    session = manager.get(session_id)

    if not session:
        raise RuntimeError("Session not found")

    """
    cfg = EngineConfig(
        initial_balance=req.get("initial_balance", 1000),
        risk_per_trade=req.get("risk_per_trade", 0.01)
    )
       
    session.config = cfg
    """
    session.mode = "live"

    
    # ✅ BẮT BUỘC: start lifecycle session
    manager.start_session(session_id)

    return {
        "session_id": session_id,
        "status": "RUNNING",
        "mode": "LIVE"
    }


@router.post("/stop/{session_id}")
def stop_live(session_id: str, request: Request):

    manager = request.app.state.manager
    session = manager.get(session_id)

    if not session:
        return {"error": "session not found"}

    live.stop(session)

    return {"status": "STOPPING"}
