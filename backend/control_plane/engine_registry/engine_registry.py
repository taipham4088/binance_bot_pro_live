from typing import Dict, Callable
import threading


class EngineRegistry:

    def __init__(self):
        self._registry: Dict[str, Callable] = {}
        self._lock = threading.RLock()

    def register(self, name: str, factory: Callable):
        with self._lock:
            if name in self._registry:
                raise ValueError(f"Engine '{name}' already registered")
            self._registry[name] = factory

    def create_engine(self, name: str, *args, **kwargs):
        with self._lock:
            if name not in self._registry:
                raise ValueError(f"Engine '{name}' not registered")
            return self._registry[name](*args, **kwargs)

    def list_engines(self):
        return list(self._registry.keys())

    # 🔗 GLUE: attach engine vào session runtime
    def attach_to_session(self, session):
        """
        Attach execution components to a session runtime.
        """

        if hasattr(session, "execution_engine"):
            session.engine = session.execution_engine

        if hasattr(session, "risk_engine"):
            session.risk = session.risk_engine

        if hasattr(session, "strategy_orchestrator"):
            session.strategy = session.strategy_orchestrator

        if hasattr(session, "reversal_warning"):
            session.warning = session.reversal_warning


# ✅ singleton registry (GIỮ NGUYÊN)
engine_registry = EngineRegistry()
