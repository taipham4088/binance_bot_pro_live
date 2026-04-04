from typing import List
from backend.execution.types.intent import Intent


class ReplayStore:
    """
    Immutable store for replay inputs
    """

    def __init__(self):
        self._intents: List[Intent] = []

    def load(self, intents: List[Intent]):
        self._intents = list(intents)

    def get(self, index: int) -> Intent:
        return self._intents[index]

    def size(self) -> int:
        return len(self._intents)
