# infrastructure/binance_exchange_info.py

import requests
from backend.runtime.exchange_config import exchange_config


class BinanceExchangeInfoFetcher:
    """
    Fetch and parse exchange rules for a given symbol.
    """

    def __init__(self):
        pass

    def fetch_symbol_info(self, symbol: str) -> dict:
        url = f"{exchange_config.rest_url}/fapi/v1/exchangeInfo"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        for s in data["symbols"]:
            if s["symbol"] == symbol:
                return self._parse_symbol(s)

        raise Exception(f"Symbol not found in exchangeInfo: {symbol}")

    def _parse_symbol(self, symbol_data: dict) -> dict:
        filters = symbol_data["filters"]

        lot_size = None
        min_notional = None

        for f in filters:
            if f["filterType"] == "LOT_SIZE":
                lot_size = f
            if f["filterType"] == "MIN_NOTIONAL":
                min_notional = f

        if lot_size is None:
            raise Exception("LOT_SIZE filter not found")

        if min_notional is None:
            raise Exception("MIN_NOTIONAL filter not found")

        return {
            "min_qty": float(lot_size["minQty"]),
            "max_qty": float(lot_size["maxQty"]),
            "step_size": float(lot_size["stepSize"]),
            "min_notional": float(min_notional["notional"]),
            "price_precision": int(symbol_data["pricePrecision"]),
            "qty_precision": int(symbol_data["quantityPrecision"]),
        }
