from backend.execution.stub_execution import StubExecution
from backend.execution.shadow_execution import ShadowExecution


class ExecutionFactory:

    @staticmethod
    def build(session):

        mode = session.mode.lower()

        # =========================
        # PAPER
        # =========================
        if mode == "paper":
            return StubExecution(session_id=session.id, mode=mode)

        # =========================
        # SHADOW (soak test)
        # =========================
        if mode == "shadow":

            from execution.live_bootstrap import build_live_execution_system

            live_system = build_live_execution_system(
                config=session.config,
                event_bus=session.state_bus,
                logger=None
            )

            # 🔥 QUAN TRỌNG NHẤT
            live_system.execution_system = live_system

            session.live_system = live_system

            return live_system

        # =========================
        # LIVE (production)
        # =========================
        if mode == "live":

            from execution.live_bootstrap import build_live_execution_system

            live_system = build_live_execution_system(
                config=session.config,
                event_bus=session.state_bus,
                logger=None
            )

            # 🔥 QUAN TRỌNG NHẤT
            live_system.execution_system = live_system

            session.live_system = live_system

            return live_system

        # =========================
        raise ValueError(f"Unsupported mode: {mode}")