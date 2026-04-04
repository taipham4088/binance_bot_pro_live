import time
from typing import Callable, List


class ExecutionEvent:
    def __init__(self, type: str, execution_id: str | None = None, **payload):
        self.ts = time.time()
        self.type = type
        self.execution_id = execution_id
        self.payload = payload

    def to_dict(self):
        return {
            "ts": self.ts,
            "type": self.type,
            "execution_id": self.execution_id,
            "payload": self.payload,
        }


class ExecutionEventBus:

    def __init__(self):
        self._subs: List[Callable[[ExecutionEvent], None]] = []

    def subscribe(self, handler: Callable[[ExecutionEvent], None]):
        self._subs.append(handler)

    def emit(self, event_type: str, execution_id: str | None = None, **payload):
        event = ExecutionEvent(event_type, execution_id, **payload)
        for fn in self._subs:
            try:
                fn(event)
            except Exception as e:
                print("[EVENT BUS] subscriber error:", e)
