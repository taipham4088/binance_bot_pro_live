"""
Session id -> TradeJournal for analytics_bus routing (live / shadow / live_shadow isolation).
"""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.RLock()
_journals: dict[str, Any] = {}


def register_trade_journal(session_id: str, journal) -> None:
    if not session_id or journal is None:
        return
    with _lock:
        _journals[str(session_id)] = journal


def unregister_trade_journal(session_id: str) -> None:
    if not session_id:
        return
    with _lock:
        _journals.pop(str(session_id), None)


def get_trade_journal(session_id: str):
    if not session_id:
        return None
    with _lock:
        return _journals.get(str(session_id))
