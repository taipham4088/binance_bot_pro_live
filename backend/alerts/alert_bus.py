from __future__ import annotations

import queue
from typing import Optional

from backend.alerts.alert_types import Alert

_DEFAULT_MAX = 2048


class AlertBus:
    """
    Thread-safe, bounded FIFO for alerts. publish() is non-blocking (drops when full).
    """

    def __init__(self, maxsize: int = _DEFAULT_MAX) -> None:
        self._q: queue.Queue[Alert] = queue.Queue(maxsize=maxsize)

    def publish(self, alert: Alert) -> None:
        try:
            self._q.put_nowait(alert)
        except queue.Full:
            pass

    def get(self) -> Optional[Alert]:
        try:
            return self._q.get_nowait()
        except queue.Empty:
            return None


alert_bus = AlertBus()
