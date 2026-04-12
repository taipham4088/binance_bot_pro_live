import sqlite3
import os
from threading import Lock
import time

from backend.storage.mode_storage import mode_storage

lock = Lock()
_seen_orders = set()
_seen_fallback = set()


def init_db(mode="shadow"):

    db_path = mode_storage.get_execution_path(mode)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS execution_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        mode TEXT,
        symbol TEXT,
        strategy TEXT,

        time INTEGER,
        side TEXT,
        size REAL,

        signal_price REAL,
        order_price REAL,
        fill_price REAL,
        fee REAL,

        slippage REAL,
        latency REAL,

        status TEXT,
        step TEXT,
        order_id TEXT
    )
    """)

    cursor.execute("PRAGMA table_info(execution_history)")
    columns = {c[1] for c in cursor.fetchall()}
    migrations = [
        ("fee", "ALTER TABLE execution_history ADD COLUMN fee REAL"),
        ("order_price", "ALTER TABLE execution_history ADD COLUMN order_price REAL"),
        ("status", "ALTER TABLE execution_history ADD COLUMN status TEXT"),
        ("step", "ALTER TABLE execution_history ADD COLUMN step TEXT"),
        ("order_id", "ALTER TABLE execution_history ADD COLUMN order_id TEXT"),
    ]
    for col, ddl in migrations:
        if col not in columns:
            cursor.execute(ddl)
            columns.add(col)

    conn.commit()
    conn.close()


def record_execution(trace, mode="shadow"):

    db_path = mode_storage.get_execution_path(mode)

    with lock:
        # cleanup dedup cache
        if len(_seen_orders) > 10000:
            _seen_orders.clear()

        if len(_seen_fallback) > 10000:
            _seen_fallback.clear()

        # ===== DEDUP LOGIC =====
        order_id = trace.get("order_id")

        if order_id:
            if order_id in _seen_orders:
                return
            _seen_orders.add(order_id)
        else:
            key = (
                trace.get("side"),
                trace.get("size"),
                trace.get("signal_price"),
                trace.get("fill_price")
            )

            if key in _seen_fallback:
                return

            _seen_fallback.add(key)

        if trace.get("fill_price") in (None, 0, "-"):
            return

        latency = trace.get("total_latency_ms")

        if latency is None:
            latency = trace.get("latency")

        if latency is None:
            latency = 0

        row_time_ms = trace.get("event_time_ms")
        if row_time_ms is None:
            row_time_ms = int(time.time() * 1000)
        else:
            try:
                row_time_ms = int(row_time_ms)
            except (TypeError, ValueError):
                row_time_ms = int(time.time() * 1000)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        fee = trace.get("fee")
        if fee is not None:
            try:
                fee = float(fee)
            except (TypeError, ValueError):
                fee = None

        cursor.execute("""
        INSERT INTO execution_history (
            mode,
            symbol,
            strategy,
            time,
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
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mode,
            trace.get("symbol"),
            trace.get("strategy"),
            row_time_ms,
            trace.get("side"),
            trace.get("size"),
            trace.get("signal_price"),
            trace.get("order_price"),
            trace.get("fill_price"),
            fee,
            trace.get("slippage"),
            latency,
            trace.get("status"),
            trace.get("step"),
            trace.get("order_id"),
        ))

        conn.commit()
        conn.close()