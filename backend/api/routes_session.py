from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from uuid import uuid4

router = APIRouter()

class CreateSessionRequest(BaseModel):
    mode: str              # live | paper | backtest
    symbol: str | None = None
    engine: str | None = None

@router.post("/session/create")
async def create_session(req: Request, payload: CreateSessionRequest):
    manager = req.app.state.manager

    if payload.mode not in ["live", "paper", "backtest"]:
        raise HTTPException(status_code=400, detail="Invalid mode")

    session = manager.create_session(
        mode=payload.mode,
        config={
            "symbol": payload.symbol,
            "engine": payload.engine,
        },
        app=req.app
    )

    session_id = str(uuid4())
    session.id = session_id
    manager.sessions[session_id] = session

    return {
        "session_id": session_id,
        "mode": payload.mode
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

