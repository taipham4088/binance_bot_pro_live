# core/persistence/execution_journal.py

import sqlite3
import threading
import time
from typing import Optional, List, Dict, Any


class ExecutionJournal:
    """
    Append-only execution journal.

    Guarantees:
    - No UPDATE
    - No DELETE
    - Insert only
    - Thread-safe
    - Deterministic ordering by auto-increment id
    """

    def __init__(self, db_path: str = "execution_journal.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    # ==============================
    # DB INITIALIZATION
    # ==============================

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=FULL;")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    execution_id TEXT,
                    step TEXT,
                    side TEXT,
                    quantity REAL,
                    order_id TEXT,
                    status TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    freeze_flag INTEGER DEFAULT 0
                );
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_id
                ON execution_journal (execution_id);
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_event_type
                ON execution_journal (event_type);
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_session_id
                ON execution_journal (session_id);
                """
            )

            conn.commit()

    # ==============================
    # APPEND EVENT
    # ==============================

    def append_event(
        self,
        session_id: str,
        event_type: str,
        execution_id: Optional[str] = None,
        step: Optional[str] = None,
        side: Optional[str] = None,
        quantity: Optional[float] = None,
        order_id: Optional[str] = None,
        status: Optional[str] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        freeze_flag: int = 0,
    ) -> int:
        """
        Append a new event to journal.
        Returns inserted row id.
        """

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO execution_journal (
                        session_id,
                        ts,
                        event_type,
                        execution_id,
                        step,
                        side,
                        quantity,
                        order_id,
                        status,
                        error_type,
                        error_message,
                        freeze_flag
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        session_id,
                        int(time.time() * 1000),
                        event_type,
                        execution_id,
                        step,
                        side,
                        quantity,
                        order_id,
                        status,
                        error_type,
                        error_message,
                        freeze_flag,
                    ),
                )

                conn.commit()
                return cursor.lastrowid

    # ==============================
    # READ ALL EVENTS
    # ==============================

    def load_all_events(self) -> List[Dict[str, Any]]:
        """
        Load all journal events ordered by id ASC.
        Used by Replay Engine.
        """

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT *
                FROM execution_journal
                ORDER BY id ASC;
                """
            )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    # ==============================
    # LOAD EVENTS BY SESSION ID
    # ==============================

    def load_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Load journal events for a specific session.
        Multi-session safe replay.
        """

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT *
                FROM execution_journal
                WHERE session_id = ?
                ORDER BY id ASC;
                """,
                (session_id,),
            )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]        

    # ==============================
    # LOAD EVENTS BY EXECUTION ID
    # ==============================

    def load_by_execution_id(self, execution_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT *
                FROM execution_journal
                WHERE execution_id = ?
                ORDER BY id ASC;
                """,
                (execution_id,),
            )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    # ==============================
    # GET LAST EVENT
    # ==============================

    def get_last_event(self) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT *
                FROM execution_journal
                ORDER BY id DESC
                LIMIT 1;
                """
            )

            row = cursor.fetchone()
            return dict(row) if row else None
