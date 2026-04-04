import time
from typing import Callable, Dict, Optional

from backend.core.control.config_job import (
    ConfigJob,
    CONFIG_JOB_STATES,
)
from backend.core.session.lifecycle_hooks import LifecycleHooks


# =========================
# Config Job Runner
# =========================

class ConfigJobRunner:
    """
    STEP 12.2 – ConfigJobRunner

    Responsibilities:
    - Run ConfigJob state machine
    - Enforce strict lifecycle order
    - Call lifecycle hooks per step
    - Handle failure & timeout
    - NO execution logic
    """

    def __init__(
        self,
        lifecycle_hooks: LifecycleHooks,
        step_timeout_sec: float = 30.0,
    ):
        self.lifecycle_hooks = lifecycle_hooks
        self.step_timeout_sec = step_timeout_sec

        # Map state → hook function
        self._handlers: Dict[str, Callable[[ConfigJob], None]] = {
            "STOPPING_BOT": self._stop_bot,
            "CLOSING_POSITION": self._close_positions,
            "CANCELING_ORDERS": self._cancel_orders,
            "RESETTING_RUNTIME": self._reset_runtime,
            "APPLYING_CONFIG": self._apply_config,
            "BUILDING_ENGINE": self._build_engine,
            "STARTING_BOT": self._start_bot,
            "POST_SWITCH_VERIFY": self._post_verify,
        }
        self._handlers.update({
            "BUILDING_ENGINE": self._build_engine,
        })

    # -------------------------
    # Public API
    # -------------------------

    def run(self, job: ConfigJob) -> None:
        """
        Run job until DONE or FAILED.
        This method is synchronous by design.
        (Async wrapper will live above this layer.)
        """

        try:
            while job.state not in ("DONE", "FAILED"):
                next_state = self._next_state(job.state)
                if not next_state:
                    job.fail(f"No next state from {job.state}")
                    return

                job.transition(next_state)
                self._run_step(job)

        except Exception as e:
            job.fail(str(e))

    # -------------------------
    # Step Execution
    # -------------------------

    def _run_step(self, job: ConfigJob) -> None:
        """
        Execute one lifecycle step with timeout guard.
        """
        handler = self._handlers.get(job.state)

        # DONE has no handler
        if handler is None:
            if job.state == "DONE":
                return
            raise RuntimeError(f"No handler for state {job.state}")

        start_ts = time.time()
        handler(job)

        elapsed = time.time() - start_ts
        if elapsed > self.step_timeout_sec:
            raise RuntimeError(
                f"Config job step timeout: {job.state} ({elapsed:.2f}s)"
            )

    # -------------------------
    # State Transition Helper
    # -------------------------

    def _next_state(self, current_state: str) -> Optional[str]:
        if current_state not in CONFIG_JOB_STATES:
            return None

        idx = CONFIG_JOB_STATES.index(current_state)
        if idx + 1 >= len(CONFIG_JOB_STATES):
            return None

        return CONFIG_JOB_STATES[idx + 1]

    # -------------------------
    # Lifecycle Handlers
    # -------------------------

    def _stop_bot(self, job: ConfigJob) -> None:
        self.lifecycle_hooks.stop_bot(job.session_id)

    def _close_positions(self, job: ConfigJob) -> None:
        self.lifecycle_hooks.close_positions(job.session_id)

    def _cancel_orders(self, job: ConfigJob) -> None:
        self.lifecycle_hooks.cancel_orders(job.session_id)

    def _reset_runtime(self, job: ConfigJob) -> None:
        self.lifecycle_hooks.reset_runtime(job.session_id)

    def _apply_config(self, job: ConfigJob) -> None:
        self.lifecycle_hooks.apply_config(
            job.session_id,
            job.config_diff,
        )

    def _start_bot(self, job: ConfigJob) -> None:
        self.lifecycle_hooks.start_bot(job.session_id)

    def _post_verify(self, job: ConfigJob) -> None:
        self.lifecycle_hooks.post_switch_verify(job.session_id)

    def _build_engine(self, job: ConfigJob) -> None:
        self.lifecycle_hooks.build_engine(
            job.session_id,
            job.config_diff,
        )

