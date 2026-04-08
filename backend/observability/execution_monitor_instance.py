from backend.analytics.analytics_bus import analytics_bus
from backend.analytics.session_publish_context import resolve_session_id_from_call_stack
from backend.analytics.trade_journal import TradeJournal
from backend.observability.session_journal_registry import get_trade_journal
from .execution_monitor import ExecutionMonitor

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
