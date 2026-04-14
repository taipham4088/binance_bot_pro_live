from __future__ import annotations

import queue

from backend.notifications.notification_types import Notification

notification_queue: queue.Queue = queue.Queue(maxsize=500)


def publish(notification: Notification) -> None:
    try:
        notification_queue.put_nowait(notification)
    except queue.Full:
        pass
