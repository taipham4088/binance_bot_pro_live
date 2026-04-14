from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from backend.observability.execution_monitor_instance import execution_monitor

import psutil
import os
import time
process = psutil.Process(os.getpid())

router = APIRouter()
_SESSION_KEYS = frozenset({"live", "shadow", "paper", "backtest"})


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

def _backtest_engine_trades_to_history(trades: list) -> list:
    """Map DualEngine in-memory trades to dashboard history rows."""
    history = []
    for t in reversed(trades[-80:]):
        et = t.get("exit_time")
        if hasattr(et, "timestamp"):
            ts = int(et.timestamp())
        elif et is not None:
            try:
                ts = int(et)
            except (TypeError, ValueError):
                ts = 0
        else:
            ts = 0
        entry = t.get("entry") or t.get("entry_price")
        history.append(
            {
                "time": ts,
                "mode": "backtest",
                "symbol": "BTCUSDT",
                "strategy": "range_trend",
                "side": str(t.get("side") or "-").upper(),
                "size": t.get("size") if t.get("size") is not None else 1,
                "entry": entry,
                "exit": t.get("exit_price"),
                "pnl": t.get("result"),
                "fees": 0,
                "asset": "USDT",
            }
        )
    return history


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

    history = []
    cache = request.app.state.dashboard_cache
    trade_clear_time = cache.get_trade_clear_time(key)

    db_path = mode_storage.get_trade_path(key)
    if db_path and os.path.exists(db_path):
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

        for r in rows:
            row_time = r[0]
            try:
                row_time_int = int(row_time) if row_time is not None else None
            except (TypeError, ValueError):
                row_time_int = None
            if trade_clear_time is not None and row_time_int is not None and row_time_int <= trade_clear_time:
                continue
            history.append(
                {
                    "time": r[0],
                    "mode": r[1],
                    "symbol": r[2],
                    "strategy": r[3],
                    "side": r[4],
                    "size": r[5],
                    "entry": r[6],
                    "exit": r[7],
                    "pnl": r[8],
                    "fees": r[9],
                }
            )

    if key == "backtest":
        try:
            mgr = request.app.state.manager
            sess = mgr.get("backtest")
            eng = getattr(sess, "engine", None) if sess else None
            trades = list(getattr(eng, "trades", []) or [])
            if trades:
                history = _backtest_engine_trades_to_history(trades)
        except Exception:
            pass

    if trade_clear_time is not None:
        filtered = []
        for h in history:
            row_time = h.get("time")
            try:
                row_time_int = int(row_time) if row_time is not None else None
            except (TypeError, ValueError):
                row_time_int = None
            if row_time_int is not None and row_time_int <= trade_clear_time:
                continue
            filtered.append(h)
        history = filtered

    return {
        "status": "ok",
        "history": history
    }


@router.get("/api/dashboard/execution/history")
async def get_dashboard_execution_history(
    request: Request,
    session: str | None = None,
    mode: str | None = None,
):
    import sqlite3
    from backend.storage.mode_storage import mode_storage

    key = (session or mode or "").strip().lower()
    if not key or key not in _SESSION_KEYS:
        return {"status": "ok", "history": []}

    cache = request.app.state.dashboard_cache
    execution_clear_time = cache.get_execution_clear_time(key)

    db_path = mode_storage.get_execution_path(key)
    if not db_path or not os.path.exists(db_path):
        return {"status": "ok", "history": []}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                time,
                mode,
                symbol,
                strategy,
                side,
                size,
                signal_price,
                order_price,
                fill_price,
                fee,
                slippage,
                latency,
                status,
                step,
                order_id
            FROM execution_history
            ORDER BY id DESC
            LIMIT 100
            """
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        return {"status": "ok", "history": []}

    history = []
    for r in rows:
        row_time_ms = r[0]
        ts_sec = int(row_time_ms / 1000) if row_time_ms is not None else None
        if execution_clear_time is not None and ts_sec is not None and ts_sec <= execution_clear_time:
            continue
        lat = r[11]
        history.append(
            {
                "time": ts_sec,
                "timestamp": ts_sec,
                "mode": r[1],
                "symbol": r[2],
                "strategy": r[3],
                "side": r[4],
                "size": r[5],
                "signal_price": r[6],
                "order_price": r[7],
                "fill_price": r[8],
                "fee": r[9],
                "slippage": r[10],
                "latency": round(lat, 2) if lat is not None else 0,
                "status": r[12],
                "step": r[13],
                "order_id": r[14],
            }
        )
    return {"status": "ok", "history": history}


@router.post("/dashboard/clear_execution")
async def dashboard_clear_execution(request: Request):
    import sqlite3
    from backend.storage.mode_storage import mode_storage

    session_id = (request.query_params.get("session") or "").strip().lower()
    if not session_id or session_id not in _SESSION_KEYS:
        return {"status": "ok", "session": session_id, "cleared": False}

    db_path = mode_storage.get_execution_path(session_id)
    if not db_path or not os.path.exists(db_path):
        return {"status": "ok", "session": session_id, "cleared": True}

    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM execution_history")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return {"status": "ok", "session": session_id, "cleared": False}

    return {"status": "ok", "session": session_id, "cleared": True}


@router.post("/dashboard/clear_trades")
async def dashboard_clear_trades(request: Request):
    cache = request.app.state.dashboard_cache
    session_id = (request.query_params.get("session") or "live").strip().lower()
    ts = cache.mark_trade_clear(session_id, int(time.time()))
    return {"status": "ok", "session": session_id, "trade_clear_time": ts}

@router.post("/api/control/exchange")
async def set_exchange(data: dict, request: Request):

    exchange = data.get("exchange")

    request.app.state.exchange = exchange

    return {"status": "ok", "exchange": exchange}