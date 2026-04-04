from infrastructure.binance_exchange_info import BinanceExchangeInfoFetcher

fetcher = BinanceExchangeInfoFetcher()
info = fetcher.fetch_symbol_info("BTCUSDT")

print(info)
