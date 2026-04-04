import requests
from backend.runtime.exchange_config import exchange_config

class ExchangeInfoCache:
    """
    Loads and caches Binance Futures exchange trading rules.

    Provides:
    - tick_size
    - step_size
    - min_notional
    """

    BINANCE_FUTURES_URL = None

    def __init__(self):

        self.symbol_filters = {}

    # ==========================================================
    # LOAD EXCHANGE INFO
    # ==========================================================

    def load(self):

        print("[EXCHANGE INFO] loading metadata...")

        url = f"{exchange_config.rest_url}/fapi/v1/exchangeInfo"

        response = requests.get(url, timeout=10)

        data = response.json()

        for symbol_info in data["symbols"]:

            symbol = symbol_info["symbol"]

            filters = {
                "tick_size": None,
                "step_size": None,
                "min_notional": None,
            }

            for f in symbol_info["filters"]:

                if f["filterType"] == "PRICE_FILTER":
                    filters["tick_size"] = float(f["tickSize"])

                if f["filterType"] == "LOT_SIZE":
                    filters["step_size"] = float(f["stepSize"])

                if f["filterType"] == "MIN_NOTIONAL":
                    filters["min_notional"] = float(f["notional"])

            self.symbol_filters[symbol] = filters

        print(f"[EXCHANGE INFO] loaded {len(self.symbol_filters)} symbols")

    # ==========================================================
    # GET FILTERS
    # ==========================================================

    def get_filters(self, symbol: str):

        if symbol not in self.symbol_filters:
            raise ValueError(f"Symbol not found: {symbol}")

        return self.symbol_filters[symbol]

    # ==========================================================
    # GET TICK SIZE
    # ==========================================================

    def get_tick_size(self, symbol: str):

        return self.get_filters(symbol)["tick_size"]

    # ==========================================================
    # GET STEP SIZE
    # ==========================================================

    def get_step_size(self, symbol: str):

        return self.get_filters(symbol)["step_size"]

    # ==========================================================
    # GET MIN NOTIONAL
    # ==========================================================

    def get_min_notional(self, symbol: str):

        return self.get_filters(symbol)["min_notional"]