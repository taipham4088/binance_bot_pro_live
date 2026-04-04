from backend.adapters.market.binance_market_adapter import BinanceMarketAdapter
import time

def on_candle(i, row, df):
    print(i, row["time"], row["close"])

market = BinanceMarketAdapter("BTCUSDT", "1m")
market.subscribe_candle(on_candle)

while True:
    time.sleep(1)
