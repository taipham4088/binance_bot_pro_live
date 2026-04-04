from fastapi import APIRouter, Request

router = APIRouter()


# ==========================================
# GET RISK CONFIG
# ==========================================

@router.get("/risk")
def get_risk(request: Request):

    manager = request.app.state.manager

    if not manager.sessions:
        return {"error": "no active session"}

    session = list(manager.sessions.values())[0]

    return session.get_risk_config()


# ==========================================
# SET RISK CONFIG
# ==========================================

@router.post("/risk/config")
def set_risk(payload: dict, request: Request):

    manager = request.app.state.manager

    if not manager.sessions:
        return {"error": "no active session"}

    session = list(manager.sessions.values())[0]

    session.set_risk_config(payload)

    return {
        "status": "ok",
        "risk": session.get_risk_config()
    }

# ==========================================
# GET RISK STATE (RUNTIME METRICS)
# ==========================================

@router.get("/risk/state")
def get_risk_state(request: Request):

    manager = request.app.state.manager

    if not manager.sessions:
        return {"error": "no active session"}

    session = list(manager.sessions.values())[0]

    if not hasattr(session, "risk_engine"):
        return {"error": "risk engine not attached"}

    return session.risk_engine.snapshot()