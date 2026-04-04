from typing import Dict, Optional

from backend.core.run_manager import RunManager
from backend.core.control.config_job import ConfigDiff
from backend.core.session.session_lifecycle_manager import (
    SessionLifecycleManager,
)


# =========================
# Lifecycle Hooks
# =========================

class LifecycleHooks:
    """
    STEP 12.3 – LifecycleHooks

    Responsibilities:
    - Act as the ONLY adapter between ConfigJobRunner and SessionLifecycleManager
    - Forward lifecycle commands in strict order
    - NO business logic
    - NO execution logic
    """

    def __init__(self, manager: RunManager):
        self.manager = manager
        
    # -------------------------
    # Internal Helper
    # -------------------------

    def _get_session(self, session_id: str):
        session = self.manager.sessions.get(session_id)
        if not session:
            raise RuntimeError(f"Session not found: {session_id}")
        return session

    # -------------------------
    # Lifecycle Commands
    # -------------------------

    def stop_bot(self, session_id: str) -> None:
        session = self._get_session(session_id)
        session.stop()

    def close_positions(self, session_id: str) -> None:
        """
        NOTE:
        Actual position closing is handled by ExecutionEngine hooks.
        Here we only ensure bot is stopped before this step.
        """
        session = self._get_session(session_id)
        # Intentionally no direct execution here
        # Placeholder for execution hook integration
        pass

    def cancel_orders(self, session_id: str) -> None:
        """
        NOTE:
        Order cancellation handled at execution adapter layer.
        """
        session = self._get_session(session_id)
        # Placeholder – no direct logic
        pass

    def reset_runtime(self, session_id: str) -> None:
        """
        Reset session runtime state (non-persistent).
        """
        session = self._get_session(session_id)
        session.clear_active_symbol()

    def apply_config(self, session_id: str, config_diff: ConfigDiff) -> None:
        """
        Apply declarative config changes.
        """
        session = self._get_session(session_id)

        # Switch symbol (guard enforced inside session)
        if config_diff.switch_symbol is not None:
            ok = session.switch_active_symbol(config_diff.switch_symbol)
            if not ok:
                raise RuntimeError(
                    f"Failed to switch active symbol: {config_diff.switch_symbol}"
                )

        # Switch mode (handled by higher-level session recreation if needed)
        if config_diff.switch_mode is not None:
            # Mode switch requires full lifecycle restart.
            # This hook only validates presence.
            session.config.mode = config_diff.switch_mode

        # Risk updates (pass-through)
        if config_diff.risk_update:
            for k, v in config_diff.risk_update.items():
                if hasattr(session.risk_engine, k):
                    setattr(session.risk_engine, k, v)

    def start_bot(self, session_id: str) -> None:
        session = self._get_session(session_id)
        started = session.start()
        if not started:
            raise RuntimeError("Failed to start session")

    def post_switch_verify(self, session_id: str) -> None:
        """
        Final verification hook.
        """
        session = self._get_session(session_id)

        # Minimal sanity checks
        if session.state.status != "RUNNING":
            raise RuntimeError("Post-switch verify failed: session not running")

    def build_engine(self, session_id: str, config: dict):
        session = self._get_session(session_id)
        session.build_engine()


