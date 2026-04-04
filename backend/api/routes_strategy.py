from fastapi import APIRouter, Request

router = APIRouter()


# ==========================================
# GET CURRENT STRATEGY
# ==========================================

@router.get("/strategy")
def get_strategy(request: Request):

    manager = request.app.state.manager

    if not manager.sessions:
        return {"error": "no active session"}

    session = list(manager.sessions.values())[0]

    return {
        "strategy": session.get_strategy()
    }


# ==========================================
# CHANGE STRATEGY
# ==========================================

@router.post("/strategy/select")
def select_strategy(payload: dict, request: Request):

    manager = request.app.state.manager

    if not manager.sessions:
        return {"error": "no active session"}

    session = list(manager.sessions.values())[0]

    strategy = payload.get("strategy")

    if not strategy:
        return {"error": "strategy required"}

    try:
        session.set_strategy(strategy)
    except ValueError as e:
        return {"error": str(e)}

    return {
        "status": "ok",
        "strategy": session.get_strategy()
    }
