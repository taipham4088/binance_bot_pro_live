import os
import time
import psutil

from backend.alerts.alert_manager import alert_manager
from backend.alerts.alert_types import Alert, AlertLevel, AlertSource

_peak_threads: int = 0
_last_thread_drop_alert_ts: float = 0.0
_THREAD_DROP_COOLDOWN_SEC = 120.0
_THREAD_DROP_MIN_PEAK = 10
_THREAD_DROP_DELTA = 5


class SystemMetrics:
    """
    Collects runtime system metrics for monitoring a trading bot.

    Metrics:
    - CPU usage
    - Memory usage
    - Process uptime
    - Thread count
    """

    def __init__(self):

        self.process = psutil.Process(os.getpid())
        self.start_time = time.time()

    # ==========================================================
    # CPU USAGE
    # ==========================================================

    def cpu_percent(self):

        return psutil.cpu_percent(interval=None)

    # ==========================================================
    # MEMORY USAGE
    # ==========================================================

    def memory_usage_mb(self):

        mem = self.process.memory_info().rss
        return mem / (1024 * 1024)

    # ==========================================================
    # THREAD COUNT
    # ==========================================================

    def thread_count(self):

        return self.process.num_threads()

    # ==========================================================
    # UPTIME
    # ==========================================================

    def uptime_seconds(self):

        return int(time.time() - self.start_time)

    # ==========================================================
    # SNAPSHOT
    # ==========================================================

    def snapshot(self):

        global _peak_threads, _last_thread_drop_alert_ts

        threads = self.thread_count()
        _peak_threads = max(_peak_threads, threads)
        now = time.time()
        if (
            _peak_threads >= _THREAD_DROP_MIN_PEAK
            and threads <= _peak_threads - _THREAD_DROP_DELTA
            and now - _last_thread_drop_alert_ts >= _THREAD_DROP_COOLDOWN_SEC
        ):
            _last_thread_drop_alert_ts = now
            try:
                alert_manager.create_alert(
                    Alert(
                        level=AlertLevel.CRITICAL,
                        source=AlertSource.MONITORING,
                        message="Thread crash suspected (thread count dropped sharply)",
                        metadata={"threads": threads, "peak_threads": _peak_threads},
                    )
                )
            except Exception:
                pass

        return {
            "cpu_percent": self.cpu_percent(),
            "memory_mb": round(self.memory_usage_mb(), 2),
            "threads": threads,
            "uptime_sec": self.uptime_seconds(),
        }

    # ==========================================================
    # LOG STATUS
    # ==========================================================

    def print_status(self):

        data = self.snapshot()

        print("[SYSTEM METRICS]")
        print(" cpu =", data["cpu_percent"], "%")
        print(" memory =", data["memory_mb"], "MB")
        print(" threads =", data["threads"])
        print(" uptime =", data["uptime_sec"], "sec")