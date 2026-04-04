import time
from .metrics_registry import metrics_registry


def record_execution_start():
    metrics_registry.inc("execution.started")


def record_execution_completed(duration_sec: float):
    metrics_registry.inc("execution.completed")
    metrics_registry.observe("execution.duration", duration_sec)


def record_reverse_cycle(duration_sec: float):
    metrics_registry.inc("execution.reverse_cycle")
    metrics_registry.observe("execution.reverse_duration", duration_sec)


def record_execution_failure():
    metrics_registry.inc("execution.failure")
