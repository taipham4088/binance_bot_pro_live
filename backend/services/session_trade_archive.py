"""
Session trade DB archive + reset (analytics only; does not touch execution/risk engines).

Session DBs live under data/session/trades_<session>.db (see mode_storage.get_session_trade_path).
Archive append-only: data/archive/trades_archive.db
"""

from __future__ import annotations

import os
import sqlite3
import time

from backend.storage.mode_storage import mode_storage

_ALLOWED = frozenset({"live", "shadow", "paper", "backtest", "live_shadow"})


def _normalize_session(session: str) -> str:
    s = (session or "").strip().lower().replace("-", "_")
    if s not in _ALLOWED:
        raise ValueError(f"Invalid session: {session!r}")
    return s


def _ensure_archive_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS archived_trades (
            archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_session TEXT NOT NULL,
            original_trade_id INTEGER NOT NULL,
            archived_at INTEGER NOT NULL,
            mode TEXT,
            symbol TEXT,
            side TEXT,
            entry_time INTEGER,
            entry_price REAL,
            entry_size REAL,
            exit_time INTEGER,
            exit_price REAL,
            exit_size REAL,
            pnl REAL,
            fees REAL,
            duration_sec INTEGER,
            strategy TEXT,
            UNIQUE(source_session, original_trade_id)
        )
        """
    )
    conn.commit()


def archive_session_trades(session: str) -> dict:
    """
    Copy all rows from the session trades DB into the archive (INSERT OR IGNORE per source_session+trade_id).
    Does not delete from session DB (caller runs reset separately).
    """
    sid = _normalize_session(session)
    src_path = mode_storage.get_session_trade_path(sid)
    if not os.path.isfile(src_path) or os.path.getsize(src_path) == 0:
        return {"status": "ok", "session": sid, "rows_archived": 0}

    arc_path = mode_storage.get_archive_trade_path()
    os.makedirs(os.path.dirname(arc_path), exist_ok=True)
    now = int(time.time())
    archived = 0

    src = sqlite3.connect(src_path)
    try:
        cur = src.cursor()
        cur.execute(
            """
            SELECT trade_id, mode, symbol, side, entry_time, entry_price, entry_size,
                   exit_time, exit_price, exit_size, pnl, fees, duration_sec, strategy
            FROM trades
            """
        )
        rows = cur.fetchall()
    finally:
        src.close()

    if not rows:
        return {"status": "ok", "session": sid, "rows_archived": 0}

    arc = sqlite3.connect(arc_path)
    try:
        _ensure_archive_schema(arc)
        ac = arc.cursor()
        for r in rows:
            trade_id = r[0]
            ac.execute(
                """
                INSERT OR IGNORE INTO archived_trades (
                    source_session, original_trade_id, archived_at,
                    mode, symbol, side, entry_time, entry_price, entry_size,
                    exit_time, exit_price, exit_size, pnl, fees, duration_sec, strategy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (sid, trade_id, now, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13]),
            )
            if ac.rowcount and ac.rowcount > 0:
                archived += ac.rowcount
        arc.commit()
    finally:
        arc.close()

    return {"status": "ok", "session": sid, "rows_archived": archived}


def reset_session_trades_db(session: str, app_state) -> dict:
    """
    DELETE all closed trades from the session SQLite file.
    Uses the live session TradeJournal connection when the session is running.
    """
    sid = _normalize_session(session)
    manager = getattr(app_state, "manager", None)
    sess = None
    if manager and getattr(manager, "sessions", None):
        sess = manager.sessions.get(sid)

    if sess is not None:
        j = getattr(sess.system_state, "trade_journal", None)
        if j is not None and getattr(j, "conn", None):
            lock = getattr(j, "_lock", None)
            if lock:
                with lock:
                    j.conn.execute("DELETE FROM trades")
                    j.conn.commit()
            else:
                j.conn.execute("DELETE FROM trades")
                j.conn.commit()
            return {"status": "ok", "session": sid, "reset": "journal"}

    path = mode_storage.get_session_trade_path(sid)
    if not os.path.isfile(path):
        return {"status": "ok", "session": sid, "reset": "noop", "note": "no db file"}

    con = sqlite3.connect(path)
    try:
        con.execute("DELETE FROM trades")
        con.commit()
    finally:
        con.close()
    return {"status": "ok", "session": sid, "reset": "file"}
