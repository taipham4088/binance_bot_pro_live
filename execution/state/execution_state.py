# execution/state/execution_state.py
import time
from enum import Enum


class ExecutionStatus(str, Enum):
    INIT = "INIT"
    BOOTSTRAPPING = "BOOTSTRAPPING"
    SYNCING = "SYNCING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    FROZEN = "FROZEN"


class ExecutionState:
    """
    ExecutionState là 'ý thức sống' của execution system.
    Mọi layer khác chỉ được ĐỌC state, không được tự ý sửa.
    Chỉ STEP 4 (supervisor) được set_state.
    """

    def __init__(self):
        self.status: ExecutionStatus = ExecutionStatus.INIT
        self.reason: str | None = None
        self.since: float = time.time()

    # =========================
    # CORE
    # =========================

    def set_state(self, new_state: ExecutionStatus, reason: str | None = None):
        if new_state != self.status:
            old = self.status
            self.status = new_state
            self.reason = reason
            self.since = time.time()

            print(f"[EXECUTION STATE] {old.value} → {new_state.value} | {reason}")

            # 🔥 Notify system state engine if attached
            if hasattr(self, "on_change") and callable(self.on_change):
                self.on_change(self)

    # ==========================================================
    # LIFECYCLE TRANSITION HELPERS
    # ==========================================================

    def to_bootstrapping(self):
        self.set_state(ExecutionStatus.BOOTSTRAPPING, "System bootstrapping")

    def to_syncing(self):
        if self.status == ExecutionStatus.FROZEN:
            print("[LIFECYCLE] Cannot move to SYNCING from FROZEN")
            return
        self.set_state(ExecutionStatus.SYNCING, "Synchronizing with exchange")

    def to_ready(self):
        if self.status == ExecutionStatus.FROZEN:
            print("[LIFECYCLE] Cannot move to READY from FROZEN")
            return
        self.set_state(ExecutionStatus.READY, "Execution system ready")

    def to_degraded(self, reason: str):
        if self.status == ExecutionStatus.FROZEN:
            print("[LIFECYCLE] Cannot move to DEGRADED from FROZEN")
            return
        self.set_state(ExecutionStatus.DEGRADED, reason)
    # =========================
    # READ API
    # =========================
    def freeze(self, reason: str):
        if self.status == ExecutionStatus.FROZEN:
            return

        self.set_state(ExecutionStatus.FROZEN, reason)

        
    def is_ready(self) -> bool:
        return self.status == ExecutionStatus.READY

    def is_frozen(self) -> bool:
        return self.status == ExecutionStatus.FROZEN

    def can_trade(self) -> bool:
        return self.status in (
            ExecutionStatus.READY,
            ExecutionStatus.DEGRADED
        )

    def snapshot(self) -> dict:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "since": self.since,
            "uptime": round(time.time() - self.since, 2)
        }
