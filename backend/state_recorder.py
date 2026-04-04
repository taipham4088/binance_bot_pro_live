# state_recorder.py
import json
import os
import threading
from typing import Dict, Any


class StateRecorder:
    """
    Ghi raw WS messages (SNAPSHOT / DELTA) theo NDJSON.
    - 1 file / 1 session_id
    - Replay-safe
    """

    def __init__(self, base_dir: str = "recordings", enabled: bool = True):
        self.base_dir = base_dir
        self.enabled = enabled
        self._locks: Dict[str, threading.Lock] = {}

        if self.enabled:
            os.makedirs(self.base_dir, exist_ok=True)

    def _get_lock(self, session_id: str) -> threading.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = threading.Lock()
        return self._locks[session_id]

    def record(self, message: Dict[str, Any]) -> None:
        """
        message = raw dict emit ra WS
        """
        if not self.enabled:
            return

        session_id = message.get("session_id")
        if not session_id:
            return  # silently ignore

        file_path = os.path.join(self.base_dir, f"{session_id}.ndjson")
        line = json.dumps(message, separators=(",", ":"))

        lock = self._get_lock(session_id)
        with lock:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
