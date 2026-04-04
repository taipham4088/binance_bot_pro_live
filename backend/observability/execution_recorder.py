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
        fill_price REAL,

        slippage REAL,
        latency REAL
    )
    """)

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

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO execution_history (

            mode,
            symbol,
            strategy,

            time,
            side,
            size,

            signal_price,
            fill_price,

            slippage,
            latency

        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (

            mode,
            trace.get("symbol"),
            trace.get("strategy"),

            int(time.time() * 1000),
            trace.get("side"),
            trace.get("size"),

            trace.get("signal_price"),
            trace.get("fill_price"),

            trace.get("slippage"),
            latency
        ))

        conn.commit()
        conn.close()