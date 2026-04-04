from fastapi import APIRouter, Request
from fastapi import APIRouter, Body, HTTPException
router = APIRouter()

# =========================
# STATE & HEALTH API
# =========================

@router.get("/snapshot")
def snapshot(request: Request):
    manager = request.app.state.manager
    return manager.snapshot()


@router.get("/health")
def health(request: Request):
    manager = request.app.state.manager
    return manager.health()

# ✅ CHECK SYSTEM – PRE-FLIGHT
@router.get("/check")
def check_system(request: Request):
    engine = request.app.state.health_engine
    return engine.run_full_check()   

@router.post("/broadcast")
async def broadcast_state(req: Request):
    body = await req.json()
    session_id = body["session_id"]
    message = body["message"]

    hub = req.app.state.state_hub
    if message["type"] == "SNAPSHOT":
        await hub.emit_snapshot(session_id, message["data"])
    else:
        await hub.emit_delta(session_id, message["data"])


    return {"ok": True} 

@router.post("/dev/set-equity")
async def dev_set_equity(
    request: Request,
    session_id: str = Body(...),
    equity: float = Body(...)
):
    manager = request.app.state.manager
    session = manager.sessions.get(session_id)

    print("===== DEV SET EQUITY DEBUG =====")
    print("session =", session)
    print("engine =", session.engine)
    print("engine attrs =", dir(session.engine))

    if hasattr(session.engine, "sync_engine"):
        print("sync_engine =", session.engine.sync_engine)
        print("sync_engine attrs =", dir(session.engine.sync_engine))

    return {"ok": False}






