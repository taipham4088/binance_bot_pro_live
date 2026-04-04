# backend/execution/mode_router.py

from backend.adapters.execution.dummy_execution_adapter import DummyExecutionAdapter


class ModeRouter:

    def __init__(self, mode: str, live_system, orchestrator):
        self.mode = mode.lower()
        self.live_system = live_system
        self.orchestrator = orchestrator

    def build_execution_port(self):

        if self.mode == "paper":
            return DummyExecutionAdapter(self.orchestrator)

        if self.mode == "shadow":
            # tạm thời vẫn dùng dummy
            # sau này sẽ wrap real + dummy compare
            return DummyExecutionAdapter(self.orchestrator)

        if self.mode == "live":
            return self.live_system

        raise ValueError(f"Unsupported mode: {self.mode}")
