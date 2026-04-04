from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio

router = APIRouter()

@router.websocket("/ws/state/{session_id}")
async def ws_state(websocket: WebSocket, session_id: str):

    app = websocket.app
    hub = app.state.state_hub
    manager = app.state.manager

    print("[STATE_WS] connect:", session_id)

    # register (hub accept bên trong)
    await hub.register(session_id, websocket)

    # chờ session RUNNING
    while True:
        session = manager.sessions.get(session_id)
        if session and session.status == session.STATUS_RUNNING:
            break
        await asyncio.sleep(0.2)

    print("[STATE_WS] emitting snapshot to new subscriber")

    # 🔥 EMIT LẠI snapshot cho subscriber mới
    await session.system_state.emit_snapshot()

    try:
        while True:
            await websocket.receive_text()

    except Exception:
        await hub.unregister(session_id, websocket)
        print("[STATE_WS] disconnected:", session_id)
