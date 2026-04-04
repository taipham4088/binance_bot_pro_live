from backend.execution.timeline.timeline_engine import TimelineEngine
from backend.execution.replay.replay_store import ReplayStore
from backend.execution.types.intent import Intent


class ReplayEngine:
    """
    Offline replay over TimelineEngine
    """

    def __init__(self, timeline: TimelineEngine, store: ReplayStore):
        self._timeline = timeline
        self._store = store
        self._cursor = 0

    def reset(self):
        self._cursor = 0

    def step(self):
        if self._cursor >= self._store.size():
            return None

        intent: Intent = self._store.get(self._cursor)
        event = self._timeline.step(intent)
        self._cursor += 1
        return event

    def run(self):
        events = []
        while self._cursor < self._store.size():
            events.append(self.step())
        return events

    def seek(self, index: int):
        """
        Seek = reset + replay until index
        """
        if index < 0:
            index = 0
        if index > self._store.size():
            index = self._store.size()

        self.reset()
        while self._cursor < index:
            self.step()

    def cursor(self) -> int:
        return self._cursor
