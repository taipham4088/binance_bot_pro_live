from __future__ import annotations

import time

from backend.notifications.notification_manager import notification_manager
from backend.notifications.notification_types import Notification, NotificationType


def notify_position_open(symbol: str, side: str, session: str | None = None) -> None:
    try:
        sym = (symbol or "").upper()
        notification_manager.emit_trading_notification(
            Notification(
                type=NotificationType.POSITION_OPEN,
                message=f"{side} opened {sym}",
                level="INFO",
                source="trading",
                session=session,
                symbol=sym or None,
                timestamp=time.time(),
            )
        )
    except Exception:
        pass


def notify_position_close(symbol: str, session: str | None = None) -> None:
    try:
        sym = (symbol or "").upper()
        notification_manager.emit_trading_notification(
            Notification(
                type=NotificationType.POSITION_CLOSE,
                message=f"Position closed {sym}",
                level="INFO",
                source="trading",
                session=session,
                symbol=sym or None,
                timestamp=time.time(),
            )
        )
    except Exception:
        pass


def notify_position_reverse(symbol: str, side: str, session: str | None = None) -> None:
    try:
        sym = (symbol or "").upper()
        notification_manager.emit_trading_notification(
            Notification(
                type=NotificationType.POSITION_REVERSE,
                message=f"Reverse {side} {sym}",
                level="INFO",
                source="trading",
                session=session,
                symbol=sym or None,
                timestamp=time.time(),
            )
        )
    except Exception:
        pass
