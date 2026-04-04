import time
import signal
import sys

from backend.execution.timeline.timeline_engine import TimelineEngine
from backend.execution.orchestrator.execution_orchestrator import ExecutionOrchestrator
from backend.execution.adapter.paper_adapter import PaperExecutionAdapter
from backend.execution.emission.state_emitter import StateEmitter
from backend.execution.types.execution_state import ExecutionState
from backend.execution.orchestrator.execution_context import ExecutionContext
from backend.execution.types.intent import Intent


# -----------------------------
# GRACEFUL SHUTDOWN
# -----------------------------
running = True

def stop(sig, frame):
    global running
    running = False
    print("🛑 Stopping paper runner...")

signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)


# -----------------------------
# INITIAL STATE (PAPER)
# -----------------------------
initial_state = ExecutionState(
    meta={"timeline_index": 0},
    authority="paper",
    health="normal",
    execution_state="IDLE",
    position={"side": "flat", "size": 0},
    risk={},
    last_decision={},
)

context = ExecutionContext(
    authority="paper",
    position={"side": "flat", "size": 0},
    risk={
        "risk_pct": 0.01
    },
    health="normal",
    kill_switch=False,
)


engine = TimelineEngine(
    orchestrator=ExecutionOrchestrator(),
    initial_state=initial_state,
    context=context,
    paper_adapter=PaperExecutionAdapter(),
    emitter=StateEmitter(),
)

print("🚀 PAPER runner started")


# -----------------------------
# MAIN LOOP
# -----------------------------
while running:
    intent = Intent(
        intent_id="paper-test-1",
        session_id="paper",
        source="manual",
        type="open_long",
        payload={
            "symbol": "BTCUSDT",
            "risk": 0.01
        },
        timestamp=int(time.time() * 1000),
    )


    event = engine.step(intent)

    print(
        f"[PAPER] step={event.index} "
        f"state={engine.current_state().execution_state} "
        f"pos={engine.current_state().position}"
    )

    time.sleep(5)   # ⬅️ chỉnh 1–5s tuỳ bạn
