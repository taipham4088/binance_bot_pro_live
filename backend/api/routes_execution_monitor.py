from fastapi import APIRouter
from backend.observability.execution_monitor_instance import execution_monitor
import sqlite3

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
def execution_history(mode: str | None = None):

    try:

        from backend.storage.mode_storage import mode_storage
        from backend.main import app
        import sqlite3

        # get mode runtime
        if not mode:
            manager = app.state.manager
            sessions = manager.sessions

            if sessions:
                session = list(sessions.values())[0]
                mode = session.mode
            else:
                mode = "shadow"

        db_path = mode_storage.get_execution_path(mode)

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
        fill_price,
        slippage,
        latency
        FROM execution_history
        ORDER BY id DESC
        LIMIT 50
        """)

        rows = cursor.fetchall()

        conn.close()

        history = []

        for r in rows:

            history.append({
                "time": int(r[0] / 1000),
                "mode": r[1],
                "symbol": r[2],
                "strategy": r[3],
                "side": r[4],
                "size": r[5],
                "fill_price": r[6],
                "slippage": r[7],
                "latency": round(r[8], 2) if r[8] else 0
            })

        return {
            "status": "ok",
            "history": history
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }