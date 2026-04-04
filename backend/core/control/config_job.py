import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


# =========================
# Config Job States
# =========================

CONFIG_JOB_STATES: List[str] = [
    "CREATED",
    "STOPPING_BOT",
    "CLOSING_POSITION",
    "CANCELING_ORDERS",
    "RESETTING_RUNTIME",
    "APPLYING_CONFIG",
    "BUILDING_ENGINE",
    "STARTING_BOT",
    "POST_SWITCH_VERIFY",
    "DONE",
    "FAILED",
]


# =========================
# Config Diff Model
# =========================

@dataclass
class ConfigDiff:
    """
    Describes requested runtime configuration changes.
    This is declarative only – no execution logic.
    """
    switch_symbol: Optional[str] = None
    switch_mode: Optional[str] = None          # live | paper | backtest
    risk_update: Optional[Dict[str, Any]] = None


# =========================
# Audit Metadata
# =========================

@dataclass
class AuditMeta:
    requested_by: str
    requested_at: float
    reason: Optional[str] = None


# =========================
# Config Job Model
# =========================

@dataclass
class ConfigJob:
    """
    STEP 12.1 – Config Job Model

    Pure state model.
    No execution, no hooks, no side effects.
    """

    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    state: str = "CREATED"

    config_diff: ConfigDiff = field(default_factory=ConfigDiff)
    audit: Optional[AuditMeta] = None

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    error: Optional[str] = None

    # -------------------------
    # State Helpers
    # -------------------------

    def can_transition(self, next_state: str) -> bool:
        """
        Enforce strict lifecycle order.
        """
        if next_state not in CONFIG_JOB_STATES:
            return False

        if self.state == "FAILED":
            return False

        if self.state == "DONE":
            return False

        current_index = CONFIG_JOB_STATES.index(self.state)
        next_index = CONFIG_JOB_STATES.index(next_state)

        # Must move forward by exactly 1 step
        return next_index == current_index + 1

    def transition(self, next_state: str) -> None:
        """
        Perform state transition.
        """
        if not self.can_transition(next_state):
            raise RuntimeError(
                f"Invalid config job transition: {self.state} → {next_state}"
            )

        self.state = next_state
        self.updated_at = time.time()

    def fail(self, reason: str) -> None:
        """
        Move job into FAILED state.
        """
        self.state = "FAILED"
        self.error = reason
        self.updated_at = time.time()

    # -------------------------
    # Read-only Snapshot
    # -------------------------

    def snapshot(self) -> dict:
        return {
            "job_id": self.job_id,
            "session_id": self.session_id,
            "state": self.state,
            "config_diff": {
                "switch_symbol": self.config_diff.switch_symbol,
                "switch_mode": self.config_diff.switch_mode,
                "risk_update": self.config_diff.risk_update,
            },
            "audit": {
                "requested_by": self.audit.requested_by if self.audit else None,
                "requested_at": self.audit.requested_at if self.audit else None,
                "reason": self.audit.reason if self.audit else None,
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }

    
