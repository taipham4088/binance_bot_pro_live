from fastapi import WebSocket
from typing import Dict, Set

from backend.execution.emission.state_emitter import StateEmitter
from backend.execution.timeline.timeline_engine import TimelineEngine


class ExecutionWS:
    """
    Read-only WebSocket bridge for Execution State
    - Push-only
    - Snapshot first, then delta
    """

    def __init__(self, engine: TimelineEngine):
        self._engine = engine
        self._emitter = StateEmitter()
        self._clients: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)

        # SNAPSHOT ngay khi connect
        msg = self._emitter.emit(self._engine.current_state())
        await ws.send_json(msg)

    async def disconnect(self, ws: WebSocket):
        if ws in self._clients:
            self._clients.remove(ws)

    async def broadcast(self):
        """
        Gọi sau mỗi timeline step
        """
        msg = self._emitter.emit(self._engine.current_state())
        for ws in list(self._clients):
            try:
                await ws.send_json(msg)
            except Exception:
                await self.disconnect(ws)
