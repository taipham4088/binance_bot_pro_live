from datetime import datetime


class HealthCheckEngine:
    """
    System Health & Pre-flight Check Engine
    """

    def __init__(self, app):
        self.app = app

    # =====================================================
    # main entry
    # =====================================================

    def run_full_check(self):
        """
        Full system pre-flight check.
        """
        report = {
            "ts": datetime.utcnow().isoformat(),
            "system": self.check_system(),
            "sessions": self.check_sessions(),
        }

        report["ok"] = all(
            block.get("ok", False) for block in report["system"].values()
        )

        return report

    # =====================================================
    # system-level
    # =====================================================

    def check_system(self):
        app = self.app

        return {
            "state_hub": self._safe(self.check_state_hub),
            "run_manager": self._safe(self.check_run_manager),
        }

    def check_state_hub(self):
        hub = getattr(self.app.state, "state_hub", None)
        if not hub:
            return {"ok": False, "msg": "StateHub not found"}

        return {
            "ok": True,
            "connections": sum(len(v) for v in hub.connections.values())
        }

    def check_run_manager(self):
        manager = getattr(self.app.state, "manager", None)
        if not manager:
            return {"ok": False, "msg": "RunManager not found"}

        return {
            "ok": True,
            "sessions": len(manager.sessions)
        }

    # =====================================================
    # session-level
    # =====================================================

    def check_sessions(self):
        manager = getattr(self.app.state, "manager", None)
        if not manager:
            return {}

        results = {}
        for sid, session in manager.sessions.items():
            results[sid] = self.check_session(session)

        return results

    def check_session(self, session):
        return {
            "status": session.state.status,
            "engine": self._safe(self.check_component, session.execution_engine),
            "risk": self._safe(self.check_component, session.risk_engine),
            "strategy": self._safe(self.check_component, session.strategy_orchestrator),
            "warning": self._safe(self.check_component, session.reversal_warning),
        }

    # =====================================================
    # helpers
    # =====================================================

    def check_component(self, component):
        if component is None:
            return {"ok": False, "msg": "detached"}

        if hasattr(component, "health_check"):
            return component.health_check()

        return {"ok": True, "msg": "no health_check, assumed ok"}

    def _safe(self, fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            return {"ok": False, "error": str(e)}
