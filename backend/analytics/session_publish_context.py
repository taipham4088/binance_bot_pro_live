"""
Map analytics_bus publishers (SyncEngine / StubExecution) to trading session ids
without changing sync_engine or the execution pipeline — stack inspection at publish time.
"""
from __future__ import annotations

import inspect
import threading
from typing import Optional

_lock = threading.RLock()
_sync_id_to_session: dict[int, str] = {}
_stub_id_to_session: dict[int, str] = {}


def register_sync_engine_session(sync_engine, session_id: str) -> None:
    if sync_engine is None or not session_id:
        return
    with _lock:
        _sync_id_to_session[id(sync_engine)] = str(session_id)


def unregister_sync_engine_session(sync_engine) -> None:
    if sync_engine is None:
        return
    with _lock:
        _sync_id_to_session.pop(id(sync_engine), None)


def register_stub_execution_session(stub_execution, session_id: str) -> None:
    if stub_execution is None or not session_id:
        return
    with _lock:
        _stub_id_to_session[id(stub_execution)] = str(session_id)


def unregister_stub_execution_session(stub_execution) -> None:
    if stub_execution is None:
        return
    with _lock:
        _stub_id_to_session.pop(id(stub_execution), None)


def resolve_session_id_from_call_stack() -> Optional[str]:
    """Walk stack for SyncEngine or StubExecution `self` and return bound session id."""
    for fr in inspect.stack():
        loc = fr.frame.f_locals
        self_obj = loc.get("self")
        if self_obj is None:
            continue
        tn = type(self_obj).__name__
        if tn == "SyncEngine":
            with _lock:
                return _sync_id_to_session.get(id(self_obj))
        if tn == "StubExecution":
            with _lock:
                return _stub_id_to_session.get(id(self_obj))
    return None
