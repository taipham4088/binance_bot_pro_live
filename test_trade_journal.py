from backend.analytics.trade_journal import TradeJournal

journal = TradeJournal()

journal.on_position_open(
    symbol="BTCUSDT",
    side="LONG",
    price=60000,
    size=0.01
)

journal.on_position_close(
    price=60200,
    size=0.01
)

print(journal.get_last_trades())