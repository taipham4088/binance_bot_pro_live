import time
from enum import Enum


class ExecutionWindowState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    CLOSING = "CLOSING"


class ExecutionWindow:

    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self.reset()

    def reset(self):
        self.state = ExecutionWindowState.CLOSED
        self.execution_id = None
        self.since_ts = None
        self.anomalies = []

    # ---------------- core API ----------------

    def open(self, execution_id: str):
        if self.state != ExecutionWindowState.CLOSED:
            raise RuntimeError("execution window already open")

        self.state = ExecutionWindowState.OPEN
        self.execution_id = execution_id
        self.since_ts = time.time()
        self._emit("ExecutionWindowOpened", exec_id=execution_id)

    def mark_closing(self, execution_id: str):
        if self.execution_id != execution_id:
            return
        self.state = ExecutionWindowState.CLOSING
        self._emit("ExecutionWindowClosing", exec_id=execution_id)

    def close(self, execution_id: str):
        if self.execution_id != execution_id:
            return

        self._emit("ExecutionWindowClosed", exec_id=execution_id)

        # ✅ giữ timestamp close
        self.state = ExecutionWindowState.CLOSED
        self.execution_id = None
        self.since_ts = time.time()
        self.anomalies = []

    def force_close(self, reason: str):
        self._emit("ExecutionWindowForceClosed", exec_id=self.execution_id, reason=reason)

        self.state = ExecutionWindowState.CLOSED
        self.execution_id = None
        self.since_ts = time.time()
        self.anomalies = []

    # ---------------- anomaly ----------------

    def record_anomaly(self, drift_event):
        if self.state == ExecutionWindowState.OPEN:
            self.anomalies.append(drift_event)
            self._emit("ExecutionWindowAnomaly", drift=drift_event)

    # ---------------- query ----------------

    def is_open(self) -> bool:
        return self.state == ExecutionWindowState.OPEN

    def is_closing(self) -> bool:
        return self.state == ExecutionWindowState.CLOSING

    def is_recently_closed(self, threshold_sec: float = 2.0) -> bool:
        """
        True nếu execution vừa đóng gần đây.
        Dùng để tránh supervisor freeze ngay sau execution.
        """
        if self.since_ts is None:
            return False

        if self.state != ExecutionWindowState.CLOSED:
            return False

        return (time.time() - self.since_ts) <= threshold_sec

    def snapshot(self):
        return {
            "state": self.state,
            "execution_id": self.execution_id,
            "since_ts": self.since_ts,
            "anomalies": len(self.anomalies),
        }

    # ---------------- utils ----------------

    def _emit(self, event, **data):
        if self.event_bus:
            self.event_bus.emit(event, **data)
