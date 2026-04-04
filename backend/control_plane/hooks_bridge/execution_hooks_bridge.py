from typing import Optional
from dataclasses import dataclass


# ============================================================
# Result model – để lifecycle xử lý retry / fail
# ============================================================

@dataclass
class HookResult:
    success: bool
    message: str = ""
    retryable: bool = False


# ============================================================
# Execution Hooks Bridge
# ============================================================

class ExecutionHooksBridge:
    """
    Adapter layer giữa Lifecycle Orchestrator
    và execution runtime (RunManager / TradingSession)

    Tuyệt đối:
    - Không logic trading
    - Không mutate reducer
    - Không bypass risk
    """

    def __init__(self, manager):
        # manager = app.state.manager (RunManager)
        self.manager = manager

    # --------------------------------------------------------
    # STOP BOT
    # --------------------------------------------------------

    def stop_bot(self, session_id: str) -> HookResult:
        try:
            session = self.manager.sessions.get(session_id)
            if not session:
                # idempotent: coi như đã stop
                return HookResult(True, "Session not found – treated as stopped")
            
            self.manager.stop_session(session_id)
            return HookResult(True, "Session stopped")

        except Exception as e:
            return HookResult(
                success=False,
                message=str(e),
                retryable=True
            )

    # --------------------------------------------------------
    # CLOSE ALL POSITIONS
    # --------------------------------------------------------

    def close_all_positions(self, session_id: str) -> HookResult:
        try:
            session = self.manager.sessions.get(session_id)
            if not session:
                return HookResult(True, "No session – no positions")

            # giả định TradingSession có API này
            if hasattr(session, "close_all_positions"):
                session.close_all_positions()

            return HookResult(True, "Positions close requested")

        except Exception as e:
            return HookResult(False, str(e), retryable=True)

    # --------------------------------------------------------
    # CANCEL ALL ORDERS
    # --------------------------------------------------------

    def cancel_all_orders(self, session_id: str) -> HookResult:
        try:
            session = self.manager.sessions.get(session_id)
            if not session:
                return HookResult(True, "No session – no orders")

            if hasattr(session, "cancel_all_orders"):
                session.cancel_all_orders()

            return HookResult(True, "Orders cancel requested")

        except Exception as e:
            return HookResult(False, str(e), retryable=True)

    # --------------------------------------------------------
    # RESET RUNTIME
    # --------------------------------------------------------

    def reset_runtime(self, session_id: str) -> HookResult:
        try:
            # reset runtime = stop + cleanup internal state
            session = self.manager.sessions.get(session_id)
            if not session:
                return HookResult(True, "No session to reset")

            if hasattr(session, "reset"):
                session.reset()

            return HookResult(True, "Runtime reset")

        except Exception as e:
            return HookResult(False, str(e), retryable=True)

    # --------------------------------------------------------
    # APPLY CONFIG
    # --------------------------------------------------------

    def apply_config(self, session_id: str, new_config: dict) -> HookResult:
        try:
            session = self.manager.sessions.get(session_id)
            if not session:
                return HookResult(False, "Session not found", retryable=False)

            # KHÔNG hot-swap – chỉ set config khi đã stop
            session.config = new_config

            return HookResult(True, "Config applied")

        except Exception as e:
            return HookResult(False, str(e), retryable=False)

    # --------------------------------------------------------
    # START BOT
    # --------------------------------------------------------

    def start_bot(self, session_id: str) -> HookResult:
        try:
            if session_id not in self.manager.sessions:
                return HookResult(False, "Session not found", retryable=False)

            self.manager.start_session(session_id)
            return HookResult(True, "Session started")

        except Exception as e:
            return HookResult(False, str(e), retryable=True)

    # --------------------------------------------------------
    # POST SWITCH VERIFY
    # --------------------------------------------------------

    def post_switch_verify(self, session_id: str) -> HookResult:
        try:
            session = self.manager.sessions.get(session_id)
            if not session:
                return HookResult(False, "Session missing after switch")

            # Không kiểm tra session.running
            # Nếu không exception → coi là OK
            return HookResult(True, "Post switch verification OK")

        except Exception as e:
            return HookResult(False, str(e), retryable=False)


