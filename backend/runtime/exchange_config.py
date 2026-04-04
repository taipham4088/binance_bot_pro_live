from dataclasses import dataclass


@dataclass
class ExchangeEndpoint:
    rest: str
    ws: str


class ExchangeConfig:
    """
    Centralized Exchange Config
    Production-safe
    Multi-exchange ready
    """

    def __init__(self, mode: str = "live", exchange: str = "binance"):

        self.exchange = exchange
        self.mode = mode

        self._config = {
            "binance": {
                "live": ExchangeEndpoint(
                    rest="https://fapi.binance.com",
                    ws="wss://fstream.binance.com"
                ),
                "testnet": ExchangeEndpoint(
                    rest="https://testnet.binancefuture.com",
                    ws="wss://stream.binancefuture.com"
                )
            }
        }

    # =========================
    # BASE URL
    # =========================

    @property
    def rest_url(self) -> str:
        return self._config[self.exchange][self.mode].rest

    @property
    def ws_url(self) -> str:
        return self._config[self.exchange][self.mode].ws

    # =========================
    # KLINE ENDPOINT
    # =========================

    def get_klines_url(self):
        return f"{self.rest_url}/fapi/v1/klines"

    # =========================
    # WS KLINE STREAM
    # =========================

    def get_ws_kline(self, symbol: str, timeframe: str):

        symbol = symbol.lower()

        return f"{self.ws_url}/ws/{symbol}@kline_{timeframe}"


# default singleton
exchange_config = ExchangeConfig(mode="live")