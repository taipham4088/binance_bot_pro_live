import time
import uuid
from enum import Enum


class ExecutionLockError(Exception): ...
class ExecutionBusy(ExecutionLockError): ...
class ExecutionBreach(ExecutionLockError): ...
class ExecutionHijack(ExecutionLockError): ...
class InvalidPhaseTransition(ExecutionLockError): ...


class ExecutionState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"


class ExecutionPhase(str, Enum):
    NONE = "NONE"
    PLANNING = "PLANNING"
    CLOSING = "CLOSING"
    OPENING = "OPENING"
    CONFIRMING = "CONFIRMING"
    ABORTING = "ABORTING"


class ExecutionLock:

    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self.reset()

    # ---------------- core state ----------------

    def reset(self):
        self.state = ExecutionState.IDLE
        self.execution_id = None
        self.intent_id = None
        self.phase = ExecutionPhase.NONE
        self.symbol = None
        self.target_side = None
        self.since_ts = None
        self.last_heartbeat = None
        self.current_step = None

    # ---------------- public API ----------------

    def acquire(self, intent) -> str:
        if self.state != ExecutionState.IDLE:
            raise ExecutionBusy("execution already running")

        exec_id = str(uuid.uuid4())

        self.state = ExecutionState.RUNNING
        self.execution_id = exec_id
        self.intent_id = getattr(intent, "id", None)
        self.symbol = getattr(intent, "symbol", None)
        self.target_side = getattr(intent, "target_side", None)
        self.phase = ExecutionPhase.PLANNING
        self.since_ts = time.time()
        self.last_heartbeat = self.since_ts

        self._emit("ExecutionStarted", exec_id=exec_id, intent=intent)

        return exec_id

    def guard(self, execution_id: str):
        if self.state != ExecutionState.RUNNING:
            raise ExecutionBreach("no active execution")
        if execution_id != self.execution_id:
            raise ExecutionHijack("execution id mismatch")

    def update_phase(self, execution_id: str, phase: ExecutionPhase):
        self.guard(execution_id)
        self.phase = phase
        self.last_heartbeat = time.time()
        self._emit("ExecutionPhaseChanged", exec_id=execution_id, phase=phase)

    def heartbeat(self, execution_id: str, step: str | None = None):
        self.guard(execution_id)
        self.last_heartbeat = time.time()
        self.current_step = step

    def release(self, execution_id: str):
        self.guard(execution_id)
        self._emit("ExecutionFinished", exec_id=execution_id)
        self.reset()

    def abort(self, reason: str, by="system"):
        if self.state != ExecutionState.RUNNING:
            return
        self.phase = ExecutionPhase.ABORTING
        self._emit("ExecutionAborted", exec_id=self.execution_id, reason=reason, by=by)
        self.reset()

    # ---------------- snapshot ----------------

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "execution_id": self.execution_id,
            "intent_id": self.intent_id,
            "phase": self.phase,
            "symbol": self.symbol,
            "target_side": self.target_side,
            "since_ts": self.since_ts,
            "last_heartbeat": self.last_heartbeat,
            "current_step": self.current_step,
        }

    # ---------------- utils ----------------

    def _emit(self, event, **data):
        if self.event_bus:
            self.event_bus.emit(event, **data)

    # 🔥 Backward compatibility for old callers
    @property
    def current_phase(self):
        return self.phase
