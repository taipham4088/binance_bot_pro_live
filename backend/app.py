from backend.ws.intent_ws import router as intent_ws_router
from backend.api.routes_session import router as session_router
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes_config import router as config_router
import backend.engines.dual_engine_registration
from backend.api.routes_state import router as state_router
from backend.core.health_engine import HealthCheckEngine
from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio

from backend.control_plane.config_job_engine.config_job_engine import ConfigJobEngine
from backend.control_plane.lifecycle_orchestrator.lifecycle_orchestrator import (
   LifecycleOrchestrator
)
from backend.control_plane.hooks_bridge.execution_hooks_bridge import ExecutionHooksBridge
from backend.core.run_manager import RunManager
from backend.api.routes_backtest import router as backtest_router
from backend.api.routes_system import router as system_router
from backend.api.routes_debug import router as debug_router
#from backend.api.routes_live import router as live_router
from backend.core.state_hub import StateHub
from backend.ws.state_ws import router as ws_router
#from backend.core.session import TradingSession
# ===== STEP 4 imports =====
from backend.execution.reconciliation.restart_guard import RestartGuard
from backend.execution.reconciliation.supervisor import ReconciliationSupervisor
from backend.execution.reconciliation.invariant_engine import InvariantEngine
from backend.execution.reconciliation.drift_detector import DriftDetector
from backend.core.session.lifecycle_hooks import LifecycleHooks
from backend.core.trading_session import TradingSession
from backend.observability.execution_recorder import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Đây là BOOT SEQUENCE của app.
    STEP 4 phải chạy ở đây.
    """

    # 1️⃣ INIT CORE OBJECTS
    app.state.state_hub = StateHub()

    manager = RunManager(app.state.state_hub)
    app.state.manager = manager
    app.state.lifecycle_hooks = LifecycleHooks(manager)

    app.state.lifecycle = LifecycleOrchestrator(
        hooks=app.state.lifecycle_hooks
    )

    app.state.config_job_engine = ConfigJobEngine(
        lifecycle=app.state.lifecycle
    )
    # ✅ Health Check Engine (Check system button)
    app.state.health_engine = HealthCheckEngine(app)

    # Sessions are created explicitly via POST /api/system/session/create (or /api/session/create).
    # No implicit bootstrap here — avoids duplicate INIT and mode clashes with runtime_config.

    # ===== APP CHẠY TỪ ĐÂY =====
    
    yield

    # ===== SHUTDOWN =====
    """
    await exchange.stop_ws()
    """
    # manager.stop()


# 1️⃣ TẠO APP
app = FastAPI(title="Trading App Backend", lifespan=lifespan)
init_db()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2️⃣ INCLUDE ROUTERS
app.include_router(backtest_router, prefix="/backtest")
app.include_router(system_router, prefix="/system")
#app.include_router(live_router, prefix="/live")
app.include_router(config_router, prefix="/system")
app.include_router(session_router, prefix="/system")
app.include_router(debug_router, prefix="/api/debug")

# ✅ STATE API (health, check, snapshot…)
app.include_router(state_router, prefix="/state")

app.include_router(ws_router)
app.include_router(intent_ws_router)

