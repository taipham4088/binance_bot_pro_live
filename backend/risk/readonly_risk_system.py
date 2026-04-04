# backend/risk/readonly_risk_system.py
import time

class ReadOnlyRiskSystem:
    """
    Phase 4.2:
    - Freeze / Block logic
    - Still NO TRADE
    """

    FREEZE_COOLDOWN_SEC = 30

    def __init__(self, session_id: str, mode: str):
        self.session_id = session_id
        self.mode = mode
        self._state = "OK"
        self._reason = None
        self._cooldown_until = None
        self._violations = []

    # =========================
    # LIFECYCLE (COMPAT)
    # =========================

    def bind_execution(self, engine):
        return  # no-op

    # =========================
    # PRE-INTENT CHECK
    # =========================

    def pre_check(self, intent):
        now = int(time.time())

        if self._state == "BLOCKED":
            return False, self.snapshot()

        if self._state == "FROZEN":
            # Cho phép CLOSE để thoát vị thế
            if intent.type == "CLOSE":
                return True, self.snapshot()

            # Cho phép UNFREEZE để mở lại hệ thống
            if intent.type == "UNFREEZE":
                return True, self.snapshot()

            return False, self.snapshot()

        return True, self.snapshot()

    # =========================
    # POST-EXECUTION EVAL
    # =========================

    def evaluate(self, intent, execution_event):
        """
        Phase 4.2:
        - FREEZE → persist until UNFREEZE
        - UNFREEZE → explicit release
        - BLOCK → hard block
        """

        if intent.type == "FREEZE":
            self._state = "FROZEN"
            self._reason = "manual_freeze_intent"
            self._cooldown_until = None   # ❗ no auto cooldown

        elif intent.type == "UNFREEZE":
            self._state = "OK"
            self._reason = None
            self._cooldown_until = None

        elif intent.type == "BLOCK":
            self._state = "BLOCKED"
            self._reason = "manual_block_intent"

        return self.snapshot()


    # =========================
    # SNAPSHOT
    # =========================

    def snapshot(self):
        return {
            "state": self._state,
            "reason": self._reason,
            "cooldown_until": self._cooldown_until,
            "violations": self._violations,
            "limits": {
                "max_daily_dd": None,
                "max_trades": None,
                "max_exposure": None,
            }
        }
