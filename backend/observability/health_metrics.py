from .metrics_registry import metrics_registry


# =========================================
# HEARTBEAT
# =========================================

def record_heartbeat():
    metrics_registry.inc("health.heartbeat")


# =========================================
# WS EVENTS
# =========================================

def record_ws_disconnect():
    metrics_registry.inc("health.ws_disconnect")


def record_ws_reconnect():
    metrics_registry.inc("health.ws_reconnect")


def set_ws_lag(value_ms: float):
    metrics_registry.set_gauge("health.ws_lag_ms", value_ms)


# =========================================
# REAL DEGRADED STATE
# =========================================

def record_health_degraded(reason: str | None = None):
    metrics_registry.inc("health.degraded")
    if reason:
        metrics_registry.inc(f"health.degraded.reason.{reason}")
