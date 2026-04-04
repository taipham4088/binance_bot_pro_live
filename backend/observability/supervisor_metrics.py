from .metrics_registry import metrics_registry


def record_supervisor_mode(mode: str):
    metrics_registry.inc(f"supervisor.mode.{mode}")


def record_freeze(reason: str):
    metrics_registry.inc(f"freeze.reason.{reason}")


def record_drift_detected():
    metrics_registry.inc("reconcile.drift_detected")
