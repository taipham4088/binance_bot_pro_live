from fastapi import APIRouter
from backend.observability.execution_monitor_instance import execution_monitor
import sqlite3
import os

router = APIRouter(prefix="/api/execution", tags=["execution"])


@router.get("/monitor")
def execution_monitor_snapshot():

    try:
        data = execution_monitor.snapshot()

        # 🔥 nếu restart chưa có execution
        if not data or data.get("side") in (None, "-", "flat"):

            try:
                from backend.main import app

                manager = app.state.manager
                sessions = manager.sessions

                if sessions:
                    session = list(sessions.values())[0]

                    state = session.system_state.state
                    execution = state.get("execution", {})
                    positions = execution.get("positions", [])

                    if positions:
                        p = positions[0]

                        return {
                            "status": "ok",
                            "state": "READY",
                            "side": p.get("side"),
                            "size": p.get("size"),
                            "price": p.get("entry_price"),
                            "synthetic": True
                        }

            except Exception:
                pass

        if not data:
            return {"status": "empty"}

        return {
            "status": "ok",
            **data
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }

from backend.core.persistence.execution_journal import ExecutionJournal

@router.get("/history")
def execution_history(session: str | None = None, mode: str | None = None):

    try:

        from backend.storage.mode_storage import mode_storage

        # Strict session isolation: never fallback to active/first/shadow session.
        mode_key = (session or mode or "").strip().lower()
        if not mode_key:
            return {"status": "ok", "history": []}

        db_path = mode_storage.get_execution_path(mode_key)
        if not db_path or not os.path.exists(db_path):
            return {"status": "ok", "history": []}

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
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
        LIMIT 50
        """)

        rows = cursor.fetchall()

        conn.close()

        history = []

        for r in rows:
            row_time_ms = r[0]
            ts_sec = int(row_time_ms / 1000) if row_time_ms is not None else None
            lat = r[11]
            history.append({
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
            })

        return {
            "status": "ok",
            "history": history
        }

    except Exception as e:
        # Missing table/db or any read issue should not fallback/cross-session.
        return {
            "status": "ok",
            "history": [],
            "message": str(e)
        }