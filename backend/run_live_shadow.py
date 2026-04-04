import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import time
import signal

from backend.risk.risk_engine import RiskEngine
from backend.execution.shadow_execution import ShadowExecution
from backend.execution.timeline.timeline_engine import TimelineEngine
from backend.execution.orchestrator.execution_orchestrator import ExecutionOrchestrator
from backend.execution.orchestrator.execution_context import ExecutionContext

from backend.execution.emission.state_emitter import StateEmitter
from backend.execution.types.execution_state import ExecutionState
from backend.execution.types.intent import Intent

from backend.adapters.market.binance_market_adapter import BinanceMarketAdapter
from execution.adapter.binance.binance_adapter import BinanceExecutionAdapter

# =============================
# CONFIG
# =============================
SESSION_ID = "live_shadow"
SYMBOL = "BTCUSDT"
TIMEFRAME = "5m"
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

# =============================
# GRACEFUL SHUTDOWN
# =============================
running = True

def stop(sig, frame):
    global running
    running = False
    print("🛑 Stopping LIVE SHADOW runner...")

signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

# =============================
# POSITION SYNC FROM EXCHANGE
# =============================

print("🔍 Syncing position from Binance...")

def _noop_user_event(event):
    pass

execution_adapter = BinanceExecutionAdapter(
    api_key=API_KEY,
    api_secret=API_SECRET,
    on_user_event=_noop_user_event,
    execution_state=None,
    execution_lock=None,
    symbol=SYMBOL
)

exchange_positions = execution_adapter.get_positions()

synced_side = "flat"
synced_size = 0

for p in exchange_positions:
    if p.symbol == SYMBOL:
        synced_side = "long" if p.side == "LONG" else "short"
        synced_size = p.size
        print(f"📌 Exchange position detected: {synced_side} {synced_size}")
        break

if synced_side == "flat":
    print("📌 No position on exchange")

# =============================
# INITIAL STATE (LIVE SHADOW)
# =============================
initial_state = ExecutionState(
    meta={"timeline_index": 0},
    authority="live-trade",
    health="normal",
    execution_state="IDLE",
    position={"side": synced_side, "size": synced_size},
    risk={"kill_switch": False},
    last_decision={}
)


# =============================
# EXECUTION CONTEXT
# =============================
context = ExecutionContext(
    authority="live-trade",
    position={"side": synced_side, "size": synced_size},
    risk={},
    health="normal",
    kill_switch=False
)

# =============================
# RISK ENGINE
# =============================
risk_engine = RiskEngine()


# =============================
# CORE ENGINE
# =============================
emitter = StateEmitter()

shadow_adapter = ShadowExecution(
    session_id=SESSION_ID,
    mode="shadow"
)

engine = TimelineEngine(
    orchestrator=ExecutionOrchestrator(),
    initial_state=initial_state,
    context=context,
    live_adapter=shadow_adapter,
    emitter=emitter,
)
# expose risk engine for API
engine.risk_engine = risk_engine

# =============================
# LIVE MARKET (BINANCE FUTURES)
# =============================
market = BinanceMarketAdapter(
    symbol=SYMBOL,
    timeframe=TIMEFRAME
)


print("🚀 LIVE SHADOW FUTURES runner started")
print("🔓 authority = live-trade")
print("📡 market = BINANCE FUTURES")
print("⚡ execution = ENABLED")
print("🆔 session =", SESSION_ID)


# =============================
# MARKET CALLBACK
# =============================
def on_candle(*args):

    try:
        row = args[1]

        print(
            "[CANDLE]",
            row["time"],
            row["close"],
            "EMA200_1H=", row.get("ema200"),
            "LONG=", row.get("valid_long"),
            "SHORT=", row.get("valid_short"),
            "R_HIGH=", row.get("range_high"),
            "R_LOW=", row.get("range_low")
        )

        state = engine.current_state()

        if hasattr(state, "state"):
            state = state.state

        pos = shadow_adapter._get_current_position(SYMBOL)

        if pos:
            current_pos = {
                "side": (pos.get("side") or "flat").lower(),
                "size": pos["size"]
            }
        else:
            current_pos = {
                "side": "flat",
                "size": 0
            }

        print("DEBUG ENGINE STATE:", state)

        print(
            f"[LIVE SHADOW] "
            f"state={state.execution_state} "
            f"pos={current_pos}"
        )

    except Exception as e:
        print("[CANDLE ERROR]", e)
# =============================
# SUBSCRIBE MARKET
# =============================
market.subscribe_candle(on_candle)


# =============================
# MAIN LOOP (KEEP PROCESS ALIVE)
# =============================
while running:
    time.sleep(1)


market.close()
print("✅ LIVE SHADOW stopped")
