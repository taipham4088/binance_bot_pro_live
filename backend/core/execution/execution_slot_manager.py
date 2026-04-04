import time
from dataclasses import dataclass
from typing import Dict, Optional


# =========================
# Execution Slot Data Model
# =========================

@dataclass(frozen=True)
class ExecutionSlotKey:
    exchange: str
    environment: str   # live | paper
    api_key: str


@dataclass
class ExecutionSlotRecord:
    session_id: str
    mode: str          # live | paper | backtest
    acquired_at: float


# =========================
# Execution Slot Manager
# =========================

class ExecutionSlotManager:
    """
    Enforces:
    - 1 execution slot / account
    - Priority: LIVE > PAPER > BACKTEST
    - No execution authority (slot control only)
    """

    def __init__(self):
        self._slots: Dict[ExecutionSlotKey, ExecutionSlotRecord] = {}

    # -------------------------
    # Priority Rule (HARD CODED)
    # -------------------------
    def _priority(self, mode: str) -> int:
        if mode == "live":
            return 3
        if mode == "paper":
            return 2
        if mode == "backtest":
            return 1
        raise ValueError(f"Unknown mode: {mode}")

    # -------------------------
    # Slot Acquire
    # -------------------------
    def acquire_slot(
        self,
        key: ExecutionSlotKey,
        session_id: str,
        mode: str
    ) -> bool:
        """
        Try to acquire execution slot for a session.
        Return True if acquired, False if rejected.
        """

        now = time.time()

        # Slot is free → acquire
        if key not in self._slots:
            self._slots[key] = ExecutionSlotRecord(
                session_id=session_id,
                mode=mode,
                acquired_at=now
            )
            return True

        current = self._slots[key]

        # Idempotent: same session re-acquire
        if current.session_id == session_id:
            return True

        # Higher priority preempts lower priority
        if self._priority(mode) > self._priority(current.mode):
            self._slots[key] = ExecutionSlotRecord(
                session_id=session_id,
                mode=mode,
                acquired_at=now
            )
            return True

        # Lower or equal priority → reject
        return False

    # -------------------------
    # Slot Release
    # -------------------------
    def release_slot(self, key: ExecutionSlotKey, session_id: str) -> None:
        """
        Release slot only if owned by the session.
        Silent no-op otherwise.
        """

        current = self._slots.get(key)
        if not current:
            return

        if current.session_id != session_id:
            return

        del self._slots[key]

    # -------------------------
    # Read-only Debug / Observer
    # -------------------------
    def get_slot_info(self, key: ExecutionSlotKey) -> Optional[ExecutionSlotRecord]:
        return self._slots.get(key)
