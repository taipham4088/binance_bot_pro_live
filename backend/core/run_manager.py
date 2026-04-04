from typing import Dict, List, Optional
from backend.core.trading_session import TradingSession
from backend.reconciliation.reconciliation_hub import ReconciliationHub

class RunManager:
    """
    App Session Manager

    - create trading sessions
    - manage lifecycle
    - expose to API layer
    """

    def __init__(self, state_hub):
        self.sessions = {}
        self.state_hub = state_hub
        self.active_session_id = None

        # 🔵 SYSTEM-LEVEL reconciliation
        self.reconciliation_hub = ReconciliationHub(
            session_id="SYSTEM",
            mode="pairwise",
            state_hub=self.state_hub,
        )

    # =====================================================
    # registry
    # =====================================================

    def register(self, session: TradingSession):
        self.sessions[session.id] = session

    def get(self, session_id: str) -> Optional[TradingSession]:
        return self.sessions.get(session_id)

    def list_sessions(self) -> List[TradingSession]:
        return list(self.sessions.values())

    def get_active(self) -> Optional[TradingSession]:
        if self.active_session_id:
            return self.sessions.get(self.active_session_id)
        return None

    # =====================================================
    # lifecycle
    # =====================================================

    def create_session(self, mode, config, app=None) -> TradingSession:
        session = TradingSession(mode=mode, config=config, app=app)

        # 🔥 PHASE 3.2 – ATTACH ENGINE ĐÚNG
        session.state_engine = session.system_state

        self.register(session)

        if app and hasattr(app.state, "state_hub"):
            print("[RUN_MANAGER] bind session to hub id =", id(app.state.state_hub))

        return session


    def start_session(self, session_id: str):
        session = self.get(session_id)
        if not session:
            raise ValueError("Session not found")

        if session.status != "RUNNING":
            session.start()
        else:
            print("[RUN_MANAGER] session already running:", session_id)
        self.active_session_id = session.id
        return session

    def stop_session(self, session_id: str):
        session = self.get(session_id)
        if not session:
            raise ValueError("Session not found")

        session.stop()
        if self.active_session_id == session.id:
            self.active_session_id = None
        return session

    # =====================================================
    # app bridge
    # =====================================================

    def snapshot(self):
        return {
            "active_session": self.active_session_id,
            "sessions": [s.snapshot() for s in self.sessions.values()]
        }

    def health(self):
        return {
            "active_session": self.active_session_id,
            "sessions": [s.health_check() for s in self.sessions.values()]
        }
