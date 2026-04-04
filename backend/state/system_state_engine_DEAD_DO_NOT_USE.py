# backend/state/system_state_engine.py

import time
from typing import Optional, Dict

class SystemStateEngine:
    def __init__(self, *, session_id: str, builder, state_hub):
        self.session_id = session_id
        self.builder = builder
        self.state_hub = state_hub

        self._last_snapshot: Optional[Dict] = None
        self._seq: int = 0

    # ===== SNAPSHOT =====

    async def refresh_all_and_broadcast(self):
        snapshot = self.builder.build_snapshot()
        self._seq += 1

        message = {
            "type": "SYSTEM_STATE",
            "mode": "SNAPSHOT",
            "meta": {
                "session_id": self.session_id,
                "ts": time.time(),
                "seq": self._seq,
            },
            **snapshot   # 👈 QUAN TRỌNG
        }

        self._last_snapshot = snapshot
        await self.state_hub.broadcast_snapshot(self.session_id, message)


    # ===== PATCH DIFF =====

    async def refresh_and_diff(self):
        new_snapshot = self.builder.build_snapshot()

        if self._last_snapshot is None:
            self._last_snapshot = new_snapshot
            return

        BLOCK_KEYS = [
            "system",
            "execution",
            "risk",
            "account",
            "analytics",
            "health",
        ]

        for block in BLOCK_KEYS:
            new_block = new_snapshot.get(block)
            old_block = self._last_snapshot.get(block)

            if new_block != old_block:
                await self._emit_patch(block, new_block)


        self._last_snapshot = new_snapshot

    async def _emit_patch(self, block: str, payload: dict):
        self._seq += 1
        patch = {
            "type": "SYSTEM_STATE",
            "mode": "PATCH",
            "block": block,
            "payload": payload,
            "meta": {
                "session_id": self.session_id,
                "ts": time.time(),
                "seq": self._seq,
            },
        }
        await self.state_hub.broadcast_patch(self.session_id, patch)
