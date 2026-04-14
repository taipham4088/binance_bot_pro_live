from __future__ import annotations

import threading
import time

from backend.alerts.alert_bus import alert_bus

from .notification_manager import notification_manager


def router_loop() -> None:
    while True:
        alert = alert_bus.get()
        if alert:
            try:
                notification_manager.route_alert(alert)
            except Exception:
                pass
        time.sleep(0.2)


def start_notification_router() -> None:
    thread = threading.Thread(target=router_loop, name="notification_router", daemon=True)
    thread.start()
