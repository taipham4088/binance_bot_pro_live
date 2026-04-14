from __future__ import annotations

import queue
from collections import deque
from threading import Lock
from typing import Any, Deque, Dict, List

from backend.alerts.alert_types import Alert, AlertLevel, AlertSource

MAX_ALERTS = 200
_BROADCAST_MAX = 256

# Thread-safe queue for async WS pump (non-blocking put from alert path).
alert_broadcast_queue: queue.Queue = queue.Queue(maxsize=_BROADCAST_MAX)


def _level_str(level: AlertLevel | str) -> str:
    return level.value if isinstance(level, AlertLevel) else str(level)


def _source_str(source: AlertSource | str) -> str:
    return source.value if isinstance(source, AlertSource) else str(source)


def alert_to_dict(alert: Alert) -> Dict[str, Any]:
    meta = alert.metadata
    if meta is not None:
        meta = dict(meta)
    return {
        "level": _level_str(alert.level),
        "source": _source_str(alert.source),
        "message": alert.message,
        "session": alert.session,
        "symbol": alert.symbol,
        "timestamp": float(alert.timestamp),
        "metadata": meta,
    }


class AlertStore:
    def __init__(self) -> None:
        self._alerts: Deque[Alert] = deque(maxlen=MAX_ALERTS)
        self._lock = Lock()

    def add(self, alert: Alert) -> None:
        with self._lock:
            self._alerts.appendleft(alert)
        payload = alert_to_dict(alert)
        try:
            alert_broadcast_queue.put_nowait(payload)
        except queue.Full:
            pass

    def get_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [alert_to_dict(a) for a in self._alerts]


alert_store = AlertStore()
