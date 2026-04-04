from backend.analytics.analytics_bus import analytics_bus
from backend.analytics.trade_journal import TradeJournal
from .execution_monitor import ExecutionMonitor

execution_monitor = ExecutionMonitor()
print("🔥 MONITOR INSTANCE:", id(execution_monitor))

# Trade journal instance
trade_journal = TradeJournal(mode="shadow")
print("🔥 TRADE JOURNAL INSTANCE:", id(trade_journal))

# Subscribe
analytics_bus.subscribe(execution_monitor)
analytics_bus.subscribe(trade_journal)