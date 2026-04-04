import threading
import time
from collections import defaultdict, deque
from typing import Dict, Any


class MetricsRegistry:
    """
    Thread-safe, fail-silent in-memory metrics registry.
    Never raise exception outward.
    """

    def __init__(self):
        self._counters = defaultdict(int)
        self._gauges = {}
        self._histograms = {}
        self._lock = threading.Lock()

    # ---------- COUNTERS ----------

    def inc(self, name: str, value: int = 1):
        try:
            with self._lock:
                self._counters[name] += value
        except Exception:
            pass  # fail silent

    # ---------- GAUGES ----------

    def set_gauge(self, name: str, value: float):
        try:
            with self._lock:
                self._gauges[name] = value
        except Exception:
            pass

    # ---------- HISTOGRAM ----------

    def observe(self, name: str, value: float, maxlen: int = 500):
        try:
            with self._lock:
                if name not in self._histograms:
                    self._histograms[name] = deque(maxlen=maxlen)
                self._histograms[name].append(value)
        except Exception:
            pass

    # ---------- SNAPSHOT ----------

    def snapshot(self) -> Dict[str, Any]:
        try:
            with self._lock:
                return {
                    "timestamp": time.time(),
                    "counters": dict(self._counters),
                    "gauges": dict(self._gauges),
                    "histograms": {
                        k: list(v) for k, v in self._histograms.items()
                    },
                }
        except Exception:
            return {}
        

# Global singleton (safe — no logic dependency)
metrics_registry = MetricsRegistry()
