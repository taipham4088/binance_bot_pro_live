import time

from backend.alerts.alert_manager import alert_manager
from backend.alerts.alert_types import Alert, AlertLevel, AlertSource

from .metrics_registry import metrics_registry

_WS_LAG_WARNING_MS = 5000.0
_WS_LAG_COOLDOWN_SEC = 60.0
_last_ws_lag_alert_ts: float = 0.0


# =========================================
# HEARTBEAT
# =========================================

def record_heartbeat():
    metrics_registry.inc("health.heartbeat")


# =========================================
# WS EVENTS
# =========================================

def record_ws_disconnect(connector: str | None = None):
    metrics_registry.inc("health.ws_disconnect")
    if connector:
        metrics_registry.inc(f"health.ws_disconnect.{connector}")
    try:
        alert_manager.create_alert(
            Alert(
                level=AlertLevel.CRITICAL,
                source=AlertSource.EXCHANGE,
                message="Adapter disconnected",
                metadata={"connector": connector} if connector else None,
            )
        )
    except Exception:
        pass


def record_ws_reconnect(connector: str | None = None):
    metrics_registry.inc("health.ws_reconnect")
    if connector:
        metrics_registry.inc(f"health.ws_reconnect.{connector}")
    try:
        alert_manager.create_alert(
            Alert(
                level=AlertLevel.WARNING,
                source=AlertSource.EXCHANGE,
                message="Restart detected",
                metadata={"connector": connector} if connector else None,
            )
        )
    except Exception:
        pass


def set_ws_lag(value_ms: float):
    metrics_registry.set_gauge("health.ws_lag_ms", value_ms)
    global _last_ws_lag_alert_ts
    try:
        v = float(value_ms)
    except (TypeError, ValueError):
        return
    if v < _WS_LAG_WARNING_MS:
        return
    now = time.time()
    if now - _last_ws_lag_alert_ts < _WS_LAG_COOLDOWN_SEC:
        return
    _last_ws_lag_alert_ts = now
    try:
        alert_manager.create_alert(
            Alert(
                level=AlertLevel.WARNING,
                source=AlertSource.MONITORING,
                message=f"High latency ws_lag_ms={v:.1f}",
            )
        )
    except Exception:
        pass


# =========================================
# REAL DEGRADED STATE
# =========================================

def record_health_degraded(reason: str | None = None):
    metrics_registry.inc("health.degraded")
    if reason:
        metrics_registry.inc(f"health.degraded.reason.{reason}")
