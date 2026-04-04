from backend.analytics.analytics_bus import AnalyticsEventBus
from backend.analytics.trade_journal import TradeJournal

bus = AnalyticsEventBus()

journal = TradeJournal()

bus.subscribe(journal)

bus.publish(
    "POSITION_OPEN",
    {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "price": 60000,
        "size": 0.01
    }
)

bus.publish(
    "POSITION_CLOSE",
    {
        "price": 60200,
        "size": 0.01
    }
)

print(journal.get_last_trades())