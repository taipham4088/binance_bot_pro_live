# backend/core/system_state_builder.py
import time
from backend.core.system_state_contract import new_snapshot, new_delta, deep_clone
from backend.observability.execution_monitor_instance import execution_monitor


class SystemStateBuilder:

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state = new_snapshot(session_id)
        self.boot_ts = time.time()

        # SYSTEM CORE FIELDS
        now = int(time.time() * 1000)
        self.state["system"]["session_id"] = session_id
        self.state["system"]["started_at"] = now
        self.state["system"]["state"] = "CREATED"

    # =========================
    # LIFECYCLE
    # =========================

    def refresh_all(self, *, risk=None, execution=None, account=None,
                    analytics=None, health=None, system=None):
        """Rebuild full snapshot from engines"""
        now = int(time.time() * 1000)

        if risk:
            self.update_risk(risk)

        if execution:
            self.update_execution(execution)

        if account:
            self.update_account(account)

        if analytics:
            self.update_analytics(analytics)
        # ===== Execution Monitoring =====
        try:
            exec_monitor = execution_monitor.snapshot()
            if exec_monitor:
                self.state.setdefault("observability", {})
                self.state["observability"]["execution_monitor"] = exec_monitor
        except Exception:
            pass

        if health:
            self.update_health(health)

        if system:
            self.update_system(system)

        now = int(time.time() * 1000)
        self.state["mode"] = "SNAPSHOT"
        self.state["ts"] = now

        # update uptime
        start = self.state["system"].get("started_at")
        if start:
            self.state["system"]["uptime"] = now - start
        return deep_clone(self.state)

    # =========================
    # UPDATE BLOCKS
    # =========================

    def update_risk(self, risk_state: dict):
        self.state["risk"].update(risk_state)

    def update_execution(self, execution_state: dict):
        self.state["execution"].update(execution_state)

    def update_system(self, system_state: dict):
        self.state["system"].update(system_state)

    def update_health(self, health_state: dict):
        health_state["ts"] = time.time()
        self.state["health"].update(health_state)

    def update_account(self, account_state: dict):
        self.state["account"].update(account_state)

    def update_analytics(self, analytics_state: dict):
        self.state["analytics"].update(analytics_state)

    # =========================
    # EMIT PAYLOAD
    # =========================

    def build_snapshot(self) -> dict:
        self.state["mode"] = "SNAPSHOT"
        self.state["ts"] = int(time.time() * 1000)
        return deep_clone(self.state)

    def build_delta(self, payload: dict) -> dict:
        return new_delta(self.session_id, payload)
