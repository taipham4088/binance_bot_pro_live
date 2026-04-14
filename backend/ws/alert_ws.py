from __future__ import annotations

import asyncio
import queue
from typing import Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.alerts.alert_store import alert_broadcast_queue, alert_store

router = APIRouter()

_clients: Set[WebSocket] = set()
_clients_lock = asyncio.Lock()
_broadcast_task: Optional[asyncio.Task] = None


async def _broadcast_loop() -> None:
    while True:
        await asyncio.sleep(0.25)
        batch: list = []
        while True:
            try:
                batch.append(alert_broadcast_queue.get_nowait())
            except queue.Empty:
                break
        if not batch:
            continue
        async with _clients_lock:
            targets = list(_clients)
        dead: list[WebSocket] = []
        for ws in targets:
            for item in batch:
                try:
                    await ws.send_json({"type": "alert", "alert": item})
                except Exception:
                    dead.append(ws)
                    break
        if dead:
            async with _clients_lock:
                for ws in dead:
                    _clients.discard(ws)


def start_alert_broadcast_task() -> asyncio.Task:
    global _broadcast_task
    if _broadcast_task is None or _broadcast_task.done():
        _broadcast_task = asyncio.create_task(_broadcast_loop())
    return _broadcast_task


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket) -> None:
    await websocket.accept()
    snapshot = alert_store.get_all()
    try:
        await websocket.send_json({"type": "snapshot", "alerts": snapshot})
    except Exception:
        await websocket.close()
        return

    async with _clients_lock:
        _clients.add(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with _clients_lock:
            _clients.discard(websocket)
