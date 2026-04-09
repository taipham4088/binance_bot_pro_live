from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from backend.observability.execution_monitor_instance import execution_monitor

import psutil
import os
process = psutil.Process(os.getpid())

router = APIRouter()


@router.get("/api/dashboard")
async def get_dashboard(request: Request):

    cache = request.app.state.dashboard_cache
    session_id = (request.query_params.get("session") or "live").strip().lower()
    dual_raw = (request.query_params.get("dual") or "").strip().lower()
    dual_panel = dual_raw in ("1", "true", "yes", "on")
    base = cache.get(session_id=session_id, dual_panel=dual_panel)

    exec_monitor = execution_monitor.snapshot()

    # 🔥 Restart restore execution panel
    if not exec_monitor:

        pos = base.get("position", {})

        if pos and pos.get("side") != "flat":

            print("🔥 DASHBOARD EXECUTION RESTORE")

            try:
                execution_monitor.restore_position(
                    symbol="BTCUSDT",
                    side=pos.get("side"),
                    size=pos.get("size"),
                    price=pos.get("entry_price")
                )

                exec_monitor = execution_monitor.snapshot()

            except Exception as e:
                print("EXECUTION RESTORE ERROR:", e)

    # CPU riêng bot
    cpu = process.cpu_percent(interval=None)

    # Memory riêng bot (MB)
    mem_mb = process.memory_info().rss / (1024 * 1024)

    # Memory % toàn RAM
    mem_percent = process.memory_percent()

    return {
        **base,

        "system": {
            "cpu": cpu,
            "mem_mb": mem_mb,
            "mem_percent": mem_percent
        },

        "observability": {
            "execution_monitor": exec_monitor
        }
    }

@router.get("/api/dashboard/position")
async def get_position(request: Request):

    cache = request.app.state.dashboard_cache
    session_id = (request.query_params.get("session") or "live").strip().lower()
    dual_raw = (request.query_params.get("dual") or "").strip().lower()
    dual_panel = dual_raw in ("1", "true", "yes", "on")
    return cache.get(session_id=session_id, dual_panel=dual_panel)["position"]


@router.get("/api/dashboard/pnl")
async def get_pnl(request: Request):

    cache = request.app.state.dashboard_cache
    session_id = (request.query_params.get("session") or "live").strip().lower()
    dual_raw = (request.query_params.get("dual") or "").strip().lower()
    dual_panel = dual_raw in ("1", "true", "yes", "on")
    return cache.get(session_id=session_id, dual_panel=dual_panel)["pnl"]


@router.get("/api/dashboard/risk-status")
async def get_risk_status(request: Request):

    cache = request.app.state.dashboard_cache
    session_id = (request.query_params.get("session") or "live").strip().lower()
    dual_raw = (request.query_params.get("dual") or "").strip().lower()
    dual_panel = dual_raw in ("1", "true", "yes", "on")
    return cache.get(session_id=session_id, dual_panel=dual_panel).get("risk_status") or {}


@router.get("/api/dashboard/metrics")
async def get_metrics(request: Request):

    cache = request.app.state.dashboard_cache
    session_id = (request.query_params.get("session") or "live").strip().lower()
    dual_raw = (request.query_params.get("dual") or "").strip().lower()
    dual_panel = dual_raw in ("1", "true", "yes", "on")
    return cache.get(session_id=session_id, dual_panel=dual_panel)["metrics"]


@router.get("/api/dashboard/trades")
async def get_trades(request: Request):

    cache = request.app.state.dashboard_cache
    session_id = (request.query_params.get("session") or "live").strip().lower()
    dual_raw = (request.query_params.get("dual") or "").strip().lower()
    dual_panel = dual_raw in ("1", "true", "yes", "on")
    return cache.get(session_id=session_id, dual_panel=dual_panel)["recent_trades"]

@router.get("/dashboard_v5")
async def dashboard_v5():

    return FileResponse(
        "frontend/dashboard/templates/dashboard_v5.html"
    )

@router.get("/dashboard_v7")
async def dashboard_v7():
    return FileResponse(
        "frontend/dashboard/templates/dashboard_v7.html"
    )

@router.get("/api/trades/history")
async def get_trade_history(
    request: Request,
    session_id: str | None = None,
    session: str | None = None,
    mode: str | None = None,
):

    import sqlite3
    from backend.storage.mode_storage import mode_storage

    key = (session_id or session or mode or "").strip().lower()
    # Strict session isolation: no fallback to active session or shadow.
    if not key:
        return {"status": "ok", "history": []}

    db_path = mode_storage.get_trade_path(key)
    if not db_path or not os.path.exists(db_path):
        return {"status": "ok", "history": []}

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
        entry_time,
        mode,
        symbol,
        strategy,
        side,
        entry_size,
        entry_price,
        exit_price,
        pnl,
        fees
        FROM trades
        ORDER BY trade_id DESC
        LIMIT 50
    """)

    rows = cursor.fetchall()

    conn.close()

    history = []

    for r in rows:

        history.append({

            "time": r[0],
            "mode": r[1],
            "symbol": r[2],
            "strategy": r[3],
            "side": r[4],
            "size": r[5],
            "entry": r[6],
            "exit": r[7],
            "pnl": r[8],
            "fees": r[9]

        })

    return {
        "status": "ok",
        "history": history
    }

@router.post("/api/control/exchange")
async def set_exchange(data: dict, request: Request):

    exchange = data.get("exchange")

    request.app.state.exchange = exchange

    return {"status": "ok", "exchange": exchange}