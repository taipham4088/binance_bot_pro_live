import asyncio
import time
import uuid
from collections import deque
from typing import Dict, Any

from .metrics_registry import metrics_registry


class AlertEngine:

    def __init__(self, interval_sec: int = 5):
        self.interval_sec = interval_sec
        self._running = False

        self._alerts = deque(maxlen=500)
        self._active: Dict[str, Dict] = {}
        self._last_snapshot = None

        # escalation memory
        self._history = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False

    def get_alerts(self):
        return list(self._alerts)

    async def _loop(self):
        while self._running:
            try:
                snapshot = metrics_registry.snapshot()
                self._evaluate(snapshot)
                self._last_snapshot = snapshot
            except Exception:
                pass
            await asyncio.sleep(self.interval_sec)

    # =========================================
    # EVALUATION
    # =========================================

    def _evaluate(self, snapshot: Dict[str, Any]):
        counters = snapshot.get("counters", {})
        histograms = snapshot.get("histograms", {})

        self._rule_drift_spike(counters)
        self._rule_execution_failure(counters)
        self._rule_latency(histograms)

        self._cleanup_resolved()

    # =========================================
    # RULES
    # =========================================

    def _rule_drift_spike(self, counters):

        if not self._last_snapshot:
            return

        current = counters.get("reconcile.drift_detected", 0)
        prev = self._last_snapshot.get("counters", {}).get("reconcile.drift_detected", 0)

        delta = current - prev
        if delta <= 0:
            return

        now = time.time()

        if delta >= 5:
            self._escalate("drift_spike", delta, now)

    def _rule_execution_failure(self, counters):

        failures = counters.get("execution.failure", 0)
        if failures >= 3:
            self._open_alert("execution_failure", "CRITICAL", "Execution failure spike")

    def _rule_latency(self, histograms):

        durations = histograms.get("execution.duration", [])
        if not durations:
            return

        latest = durations[-1]

        if latest > 8:
            self._open_alert(
                "latency_high",
                "WARNING",
                f"High execution latency {latest:.2f}s"
            )

    # =========================================
    # STATE MACHINE
    # =========================================

    def _open_alert(self, key: str, level: str, message: str):

        now = time.time()

        if key in self._active:
            alert = self._active[key]
            alert["count"] += 1
            alert["last_seen"] = now
            return

        alert = {
            "id": str(uuid.uuid4()),
            "key": key,
            "level": level,
            "status": "OPEN",
            "count": 1,
            "first_seen": now,
            "last_seen": now,
            "message": message,
        }

        self._active[key] = alert
        self._alerts.append(alert)

        print(f"[ALERT][{level}] {message}")

    def _escalate(self, key: str, delta: int, now: float):

        history = self._history.setdefault(key, [])
        history.append(now)

        # keep last 60s window
        history = [t for t in history if now - t <= 60]
        self._history[key] = history

        if len(history) >= 3:
            self._open_alert(
                key,
                "CRITICAL",
                f"{key} escalated (3 spikes in 60s)"
            )
        else:
            self._open_alert(
                key,
                "WARNING",
                f"{key} spike (+{delta})"
            )

    def _cleanup_resolved(self):

        now = time.time()
        resolve_after = 120

        to_remove = []

        for key, alert in self._active.items():
            if now - alert["last_seen"] > resolve_after:
                alert["status"] = "RESOLVED"
                self._alerts.append(alert)
                to_remove.append(key)

        for key in to_remove:
            del self._active[key]


# Singleton
alert_engine_instance = AlertEngine()
