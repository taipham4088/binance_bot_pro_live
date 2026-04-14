from __future__ import annotations

import os
from pathlib import Path

import threading

from backend.analytics.analytics_bus import analytics_bus
from backend.analytics.session_publish_context import resolve_session_id_from_call_stack
from backend.analytics.trade_journal import TradeJournal
from backend.alerts.alert_manager import alert_manager
from backend.alerts.alert_types import Alert
from backend.observability.session_journal_registry import get_trade_journal
from .execution_monitor import ExecutionMonitor


def _install_observability_alert_hooks() -> None:
    def _emit(
        alert: Alert | None = None,
        *,
        level: str = "CRITICAL",
        source: str = "system",
        message: str = "",
        session: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        try:
            if alert is not None:
                alert_manager.create_alert(alert)
            else:
                alert_manager.create_alert(
                    Alert(
                        level=level,
                        source=source,
                        message=message,
                        session=session,
                        metadata=metadata,
                    )
                )
        except Exception:
            pass

    data_dir = Path(__file__).resolve().parents[2] / "data"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        lock_path = data_dir / ".runner_singleton.pid"
        pid = os.getpid()
        if lock_path.exists():
            try:
                old_txt = lock_path.read_text(encoding="utf-8").strip()
                old_pid = int(old_txt)
            except (OSError, ValueError):
                old_pid = None
            if old_pid is not None and old_pid != pid:
                try:
                    import psutil

                    if psutil.pid_exists(old_pid):
                        _emit(
                            message="Duplicate runner",
                            metadata={"pid": pid, "existing_pid": old_pid},
                        )
                        return
                except Exception:
                    pass
        lock_path.write_text(str(pid), encoding="utf-8")
    except Exception:
        pass

    if not hasattr(threading, "excepthook"):
        return

    _prev = threading.excepthook

    def _thread_excepthook(args) -> None:
        try:
            tr = args.thread
            tname = type(tr).__name__ if tr is not None else "unknown"
            exc_type = getattr(args, "exc_type", None)
            exc_name = getattr(exc_type, "__name__", None) or "Exception"
            base_meta = {"thread": tname, "exc_type": exc_name}
            if tname == "LiveRunner":
                sid = None
                try:
                    sess = getattr(tr, "session", None)
                    sid = getattr(sess, "id", None) if sess is not None else None
                except Exception:
                    sid = None
                # Crash-safe: uncaught exception in LiveRunner.run — not manual stop()
                _emit(
                    level="CRITICAL",
                    source="system",
                    message="Runner crashed",
                    session=str(sid) if sid is not None else None,
                    metadata=base_meta,
                )
            else:
                _emit(
                    level="CRITICAL",
                    source="system",
                    message="Thread crashed",
                    metadata=base_meta,
                )
        except Exception:
            pass
        try:
            _prev(args)
        except Exception:
            pass

    threading.excepthook = _thread_excepthook


_install_observability_alert_hooks()

execution_monitor = ExecutionMonitor()

# Legacy journal: live_bootstrap still attaches resolver here; also fallback when stack has no session.
trade_journal = TradeJournal(mode="shadow", logical_mode="shadow")


class _SessionScopedTradeJournalRouter:
    """
    Routes TRADE / POSITION_* analytics events to the TradeJournal for the publishing session
    (resolved from SyncEngine or StubExecution on the call stack).
    """

    def _target_journal(self):
        sid = resolve_session_id_from_call_stack()
        if sid:
            j = get_trade_journal(sid)
            if j is not None:
                return j
        return trade_journal

    def on_execution_event(self, data):
        pass

    def handle_trade(self, data: dict):
        j = self._target_journal()
        if j is not None:
            j.handle_trade(data)

    def handle_event(self, event_type, data):
        j = self._target_journal()
        if j is not None:
            j.handle_event(event_type, data)


analytics_bus.subscribe(execution_monitor)
analytics_bus.subscribe(_SessionScopedTradeJournalRouter())
