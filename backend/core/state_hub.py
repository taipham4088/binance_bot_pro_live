# backend/core/state_hub.py

from typing import Dict, Set, Any
from fastapi import WebSocket
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class StateHub:
    """
    StateHub
    - Quản lý WS theo session_id
    - Cache last SNAPSHOT
    - Push-only (server -> client)
    """

    def __init__(self):
        # session_id -> set(WebSocket)
        self._clients: Dict[str, Set[WebSocket]] = {}
        # session_id -> last SNAPSHOT (dict)
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self.reactions = {}   # 👈 Phase 4.5

    # ---------- CLIENT MGMT ----------

    async def register(self, session_id: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._clients.setdefault(session_id, set()).add(ws)
            snapshot = self._snapshots.get(session_id)

        # Push SNAPSHOT immediately if exists
        if snapshot is not None:
            await self._safe_send(ws, {
                "type": "SNAPSHOT",
                "data": snapshot
            })

        logger.info(f"[StateHub] WS connected session={session_id}, clients={len(self._clients.get(session_id, []))}")

    async def unregister(self, session_id: str, ws: WebSocket):
        async with self._lock:
            clients = self._clients.get(session_id)
            if clients and ws in clients:
                clients.remove(ws)
                if not clients:
                    self._clients.pop(session_id, None)

        logger.info(f"[StateHub] WS disconnected session={session_id}")

    # ---------- EMISSION ----------

    async def emit_snapshot(self, session_id: str, snapshot: Dict[str, Any]):
        """
        Cache + broadcast SNAPSHOT
        """
        print("==== HUB EMIT SNAPSHOT ====")
        print("TO SESSION:", session_id)
        print("CONNECTED CLIENTS:", len(self._clients.get(session_id, [])))
        async with self._lock:
            self._snapshots[session_id] = snapshot
            clients = list(self._clients.get(session_id, []))

        payload = {"type": "SNAPSHOT", "data": snapshot}
        await self._broadcast(clients, payload)

    async def emit_delta(self, session_id: str, delta: Dict[str, Any]):
        """
        Broadcast DELTA (JSON Patch)
        """
        async with self._lock:
            clients = list(self._clients.get(session_id, []))

        payload = {"type": "DELTA", "data": delta}
        await self._broadcast(clients, payload)

    # ---------- INTERNAL ----------

    async def _broadcast(self, clients: Set[WebSocket], payload: Dict[str, Any]):
        if not clients:
            return

        for ws in list(clients):
            await self._safe_send(ws, payload)

    async def _safe_send(self, ws: WebSocket, payload: Dict[str, Any]):
        try:
            await ws.send_text(json.dumps(payload))
        except Exception as e:
            print(">>> WS SEND FAILED:", e)

            # 🔥 REMOVE DEAD CLIENT
            async with self._lock:
                for session_id, clients in self._clients.items():
                    if ws in clients:
                        clients.remove(ws)
                        print(f"[StateHub] removed dead WS from session={session_id}")
                        break

    async def record_reaction(self, reaction_decision):
        """
        Phase 4.5 – Persist + broadcast controlled reaction
        WS event type: REACTION
        """
        if reaction_decision is None:
            return

        key = reaction_decision.reconciliation_id or "global"

        async with self._lock:
            reaction_payload = {
                "reaction": reaction_decision.reaction.value,
                "severity": reaction_decision.severity.value,
                "reason": reaction_decision.reason,
                "freeze_execution": reaction_decision.freeze_execution,
                "notify_human": reaction_decision.notify_human,
                "escalate_human": reaction_decision.escalate_human,
                "invariants": [
                    {
                        "name": v.name,
                        "description": v.description,
                        "severity": v.severity.value,
                    }
                    for v in reaction_decision.invariants
                ],
                "created_at": reaction_decision.created_at.isoformat(),
            }

            # persist
            self.reactions[key] = reaction_payload

            # snapshot clients (copy under lock)
            clients = list(self._clients.get(key, []))

        # broadcast as independent WS event
        if clients:
            await self._broadcast(
                clients,
                {
                    "type": "REACTION",
                    "data": reaction_payload,
                }
            )
