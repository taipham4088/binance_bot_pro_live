import os
import time
import psutil


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

        return {
            "cpu_percent": self.cpu_percent(),
            "memory_mb": round(self.memory_usage_mb(), 2),
            "threads": self.thread_count(),
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