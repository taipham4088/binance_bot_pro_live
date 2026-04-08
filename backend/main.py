from fastapi import FastAPI

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.api.routes_strategy import router as strategy_router
from backend.api.routes_dashboard import router as dashboard_router
from backend.api.routes_session import router as session_router
from backend.api.routes_state import router as state_router
from backend.api.routes_system import router as system_router
from backend.api.routes_state_runtime import router as state_runtime_router
from backend.observability.metrics_api import router as metrics_router
from backend.api.routes_risk import router as risk_router

from backend.ws.intent_ws import router as intent_ws_router
from backend.ws.state_ws import router as state_ws_router

from backend.core.state_hub import StateHub
from backend.core.run_manager import RunManager
from backend.observability.alert_api import router as alert_router
from backend.observability.alert_engine import alert_engine_instance
from backend.analytics.trade_journal import TradeJournal
from backend.analytics.pnl_engine import PnLEngine
from backend.analytics.metrics_engine import MetricsEngine
from backend.analytics.dashboard_cache import DashboardCache
from backend.api.routes_control import router as control_router
from backend.api.routes_execution_monitor import router as execution_router
from backend.observability.execution_recorder import init_db
from backend.analytics.analytics_bus import analytics_bus
from backend.observability.execution_monitor_instance import execution_monitor
from backend.runtime.runtime_config import runtime_config, runtime_config_path
#analytics_bus.subscribe(trade_journal)
app = FastAPI(title="binance_bot_pro_live")
from backend.api.backtest import router as backtest_router
app.include_router(backtest_router)

init_db()
# =========================
# GLOBAL SYSTEM OBJECTS
# =========================

# ✅ 1️⃣ Create StateHub FIRST
app.state.state_hub = StateHub()

# ✅ 2️⃣ Create RunManager, inject state_hub
app.state.manager = RunManager(
    state_hub=app.state.state_hub
)
# =========================
# DASHBOARD ANALYTICS
# =========================

app.state.trade_journal = TradeJournal()

app.state.pnl_engine = PnLEngine()

app.state.metrics_engine = MetricsEngine()

app.state.dashboard_cache = DashboardCache(
    pnl_engine=app.state.pnl_engine,
    metrics_engine=app.state.metrics_engine,
    trade_journal=app.state.trade_journal
)

app.state.dashboard_cache.app_state = app.state

# =========================
# REST ROUTES
# =========================
app.include_router(state_runtime_router, prefix="/api")
app.include_router(session_router, prefix="/api/session")
app.include_router(state_router, prefix="/api/state")
app.include_router(system_router, prefix="/api/system")
app.include_router(strategy_router, prefix="/api")
app.include_router(risk_router, prefix="/api")
app.include_router(control_router, prefix="/api")
app.include_router(metrics_router)
app.include_router(alert_router)
app.include_router(dashboard_router)
app.include_router(execution_router)

# =========================
# WS ROUTES
# =========================
app.include_router(intent_ws_router)
app.include_router(state_ws_router)


@app.get("/")
def health():
    return {"status": "ok"}

@app.on_event("startup")
async def startup():

    print(
        "[runtime_config] loaded control panel:",
        {k: runtime_config[k] for k in ("strategy", "trade_mode", "trading_enabled", "symbol", "mode", "exchange")},
        f"file={runtime_config_path()}",
    )

    await alert_engine_instance.start()

app.mount(
    "/dashboard",
    StaticFiles(directory="frontend/dashboard"),
    name="dashboard"
)

@app.get("/dashboard")
def dashboard():
    return FileResponse("frontend/dashboard/dashboard_v5.html")

@app.get("/dashboard_v6")
def dashboard_v6():
    return FileResponse("frontend/dashboard/dashboard_v6.html")
