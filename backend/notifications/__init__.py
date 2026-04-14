"""Alert → notification routing (dashboard + optional email for CRITICAL)."""

from backend.notifications.notification_manager import notification_manager
from backend.notifications.notification_types import Notification, NotificationType

__all__ = ["Notification", "NotificationType", "notification_manager"]
