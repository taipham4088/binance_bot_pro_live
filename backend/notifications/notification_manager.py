from __future__ import annotations

import os
import smtplib
import ssl
import threading
import time
from collections import deque
from email.message import EmailMessage
from threading import Lock
from typing import Any, Deque, Dict, List, Union

from backend.alerts.alert_types import Alert, AlertLevel, AlertSource
from backend.notifications.notification_bus import publish
from backend.notifications.notification_types import Notification, NotificationType

_MAX_DASHBOARD = 100


def _level_str(level: Union[AlertLevel, str]) -> str:
    return level.value if isinstance(level, AlertLevel) else str(level)


def _source_str(source: Union[AlertSource, str]) -> str:
    return source.value if isinstance(source, AlertSource) else str(source)


def _info_to_dashboard() -> bool:
    v = os.environ.get("NOTIFY_INFO_DASHBOARD", "true").strip().lower()
    return v in ("1", "true", "yes", "on")


def _notification_to_dict(n: Notification) -> Dict[str, Any]:
    return {
        "type": n.type,
        "message": n.message,
        "level": n.level,
        "source": n.source,
        "session": n.session,
        "symbol": n.symbol,
        "metadata": n.metadata,
        "timestamp": float(n.timestamp),
    }


def _send_critical_email_async(n: Notification) -> None:
    host = os.environ.get("NOTIFY_SMTP_HOST", "").strip()
    if not host:
        return
    user = os.environ.get("NOTIFY_SMTP_USER", "").strip()
    password = os.environ.get("NOTIFY_SMTP_PASSWORD", "")
    from_addr = os.environ.get("NOTIFY_EMAIL_FROM", "").strip()
    to_addrs = os.environ.get("NOTIFY_EMAIL_TO", "").strip()
    if not from_addr or not to_addrs:
        return
    port_s = os.environ.get("NOTIFY_SMTP_PORT", "587").strip()
    try:
        port = int(port_s)
    except ValueError:
        port = 587
    use_tls = os.environ.get("NOTIFY_SMTP_TLS", "true").strip().lower() in ("1", "true", "yes")

    msg = EmailMessage()
    msg["Subject"] = f"[CRITICAL] {n.source}: {n.message[:120]}"
    msg["From"] = from_addr
    msg["To"] = to_addrs
    msg.set_content(
        f"level={n.level}\nsource={n.source}\nmessage={n.message}\n"
        f"session={n.session}\nsymbol={n.symbol}\nmetadata={n.metadata}\n"
        f"timestamp={n.timestamp}\n"
    )

    def _run() -> None:
        try:
            if use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    smtp.starttls(context=context)
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(msg)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


class NotificationManager:
    def __init__(self) -> None:
        self._history: Deque[Notification] = deque(maxlen=_MAX_DASHBOARD)
        self._lock = Lock()

    def get_recent(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [_notification_to_dict(x) for x in self._history]

    def route_alert(self, alert: Alert) -> None:
        try:
            level = _level_str(alert.level)
            source = _source_str(alert.source)
            meta = dict(alert.metadata) if alert.metadata is not None else None
            notification = Notification(
                type=NotificationType.ALERT,
                message=alert.message,
                level=level,
                source=source,
                session=alert.session,
                symbol=alert.symbol,
                metadata=meta,
                timestamp=time.time(),
            )

            if level == "CRITICAL":
                self._push_dashboard(notification)
                publish(notification)
                _send_critical_email_async(notification)
            elif level == "WARNING":
                self._push_dashboard(notification)
                publish(notification)
            elif level == "INFO":
                if _info_to_dashboard():
                    self._push_dashboard(notification)
                publish(notification)
        except Exception:
            pass

    def _push_dashboard(self, notification: Notification) -> None:
        try:
            with self._lock:
                self._history.appendleft(notification)
        except Exception:
            pass

    def emit_trading_notification(self, notification: Notification) -> None:
        """Dashboard history + notification bus; non-blocking, trading-only path."""
        try:
            self._push_dashboard(notification)
            publish(notification)
        except Exception:
            pass


notification_manager = NotificationManager()
