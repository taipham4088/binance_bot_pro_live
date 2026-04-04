import time
import uuid
import json
from pathlib import Path
from execution.journal.ExecutionRecorder import ExecutionRecorder
from execution.recovery_manager import RecoveryManager
from dotenv import load_dotenv
load_dotenv()

from backend.execution.stub_execution import StubExecution
from execution.events.event_bus import ExecutionEventBus
from backend.core.persistence.execution_journal import ExecutionJournal
from execution.system.execution_lock import ExecutionLock
from execution.system.execution_window import ExecutionWindow
from execution.reconciliation.supervisor import ReconciliationSupervisor
from execution.orchestrator.orchestrator import ExecutionOrchestrator
from execution.state.execution_state import ExecutionState
from execution.live_execution_system import LiveExecutionSystem
from execution.sync.sync_engine import SyncEngine
from execution.state.store import StateStore
from execution.adapter.exchange_factory import create_exchange_adapter


def build_live_execution_system(config, event_bus, logger):

    # 0. Execution event system
    exec_event_bus = ExecutionEventBus()

    # UI Recorder (in-memory)
    execution_recorder = ExecutionRecorder()
    exec_event_bus.subscribe(execution_recorder.on_event)

    # Crash Recovery Journal (SQLite)
    execution_journal = ExecutionJournal()

    # ==========================================================
    # 🔐 SESSION PERSISTENCE
    # ==========================================================
    SESSION_FILE = Path("session.meta")

    if SESSION_FILE.exists():
        with open(SESSION_FILE, "r") as f:
            data = json.load(f)
            session_id = data.get("session_id")
            print(f"[BOOTSTRAP] Reusing session_id: {session_id}")
    else:
        session_id = f"shadow-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        with open(SESSION_FILE, "w") as f:
            json.dump({"session_id": session_id}, f)
        print(f"[BOOTSTRAP] Created new session_id: {session_id}")

    # ==========================================================
    # 1. CORE SYSTEM
    # ==========================================================
    execution_state = ExecutionState()
    execution_state.to_bootstrapping()

    execution_lock = ExecutionLock(event_bus=exec_event_bus)
    execution_window = ExecutionWindow(event_bus=exec_event_bus)

    sync_engine = SyncEngine(event_bus=event_bus, logger=logger)

    # 👉 SINGLE SOURCE OF ANALYTICS
    analytics_stub = StubExecution(session_id=session_id, mode="live-sync")
    sync_engine.set_external_close_handler(analytics_stub.handle_external_close)

    # ==========================================================
    # 2. EXCHANGE
    # ==========================================================
    exchange = create_exchange_adapter(
        config=config,
        sync_engine=sync_engine,
        execution_state=execution_state,
        execution_lock=execution_lock
    )

    # ==========================================================
    # ❌ DISABLE REPLAY (KHÔNG DÙNG TRONG SHADOW)
    # ==========================================================
    restored_circuit_break_count = 0

    # ==========================================================
    # 3. RECOVERY (GIỮ NHẸ)
    # ==========================================================
    recovery = RecoveryManager(
        execution_state=execution_state,
        exchange_adapter=exchange,
        journal=execution_journal,
        session_id=session_id
    )

    # ==========================================================
    # 4. STATE STORE
    # ==========================================================
    state_store = StateStore()

    # ==========================================================
    # 5. LIVE SYSTEM
    # ==========================================================
    live_system = LiveExecutionSystem(
        session_id=session_id,
        exchange_adapter=exchange,
        sync_engine=sync_engine,
        state_store=state_store,
        execution_state=execution_state
    )

    live_system.execution_lock = execution_lock
    live_system.execution_window = execution_window

    supervisor = ReconciliationSupervisor(
        live_system=live_system,
        execution_window=execution_window
    )
    live_system.supervisor = supervisor

    # ==========================================================
    # 6. ORCHESTRATOR
    # ==========================================================
    orchestrator = ExecutionOrchestrator(
        execution_system=live_system,
        execution_state=execution_state,
        execution_lock=execution_lock,
        execution_window=execution_window,
        journal=execution_journal
    )

    orchestrator._consecutive_failures = restored_circuit_break_count

    live_system.orchestrator = orchestrator
    live_system.execution_journal = execution_journal
    live_system.execution_event_bus = exec_event_bus

    # ==========================================================
    # FINALIZE
    # ==========================================================
    execution_state.to_syncing()

    if not execution_state.is_frozen():
        execution_state.to_ready()
    else:
        print("[BOOTSTRAP] System remains FROZEN")

    return live_system