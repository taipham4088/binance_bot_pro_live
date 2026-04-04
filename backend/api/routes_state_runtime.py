from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

@router.get("/state/runtime/{session_id}")
def get_runtime_state(request: Request, session_id: str):
    """
    Read-only runtime state from SystemStateEngine.
    """
    manager = request.app.state.manager
    session = manager.sessions.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.system_state:
        raise HTTPException(status_code=400, detail="SystemStateEngine not ready")

    # trả về snapshot hiện tại của SystemStateEngine
    return {
        "session_id": session_id,
        "state": session.system_state.state,
    }
