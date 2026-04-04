from fastapi import APIRouter
from backend.runtime.runtime_config import runtime_config
from backend.runtime.exchange_config import exchange_config

router = APIRouter()

@router.post("/control/pause")
def pause_bot():
    runtime_config["trading_enabled"] = False
    return {"status": "paused"}

@router.post("/control/resume")
def resume_bot():
    runtime_config["trading_enabled"] = True
    return {"status": "running"}

@router.post("/control/risk")
def set_risk(risk: float):
    runtime_config["risk_percent"] = risk
    return runtime_config

@router.post("/control/trade_mode")
def set_mode(mode: str):
    runtime_config["trade_mode"] = mode
    return runtime_config

@router.post("/control/strategy")
def set_strategy(strategy: str):
    runtime_config["strategy"] = strategy
    return runtime_config

@router.post("/control/exchange")
def set_exchange(exchange: str):

    runtime_config["exchange"] = exchange

    return runtime_config

@router.post("/control/symbol")
def set_symbol(symbol: str):

    runtime_config["symbol"] = symbol

    return runtime_config


import requests
@router.get("/symbols")

def get_symbols():

    url = f"{exchange_config.rest_url}/fapi/v1/exchangeInfo"

    r = requests.get(url)

    data = r.json()

    symbols = []

    for s in data["symbols"]:

        if s["status"] == "TRADING" and s["quoteAsset"] == "USDT":

            symbols.append(s["symbol"])

    return symbols

@router.get("/market_header")
def market_header():

    import requests
    from backend.runtime.runtime_config import runtime_config

    symbol = runtime_config.get("symbol", "BTCUSDT")

    ticker_url = f"{exchange_config.rest_url}/fapi/v1/ticker/24hr?symbol={symbol}"
    ticker = requests.get(ticker_url).json()

    funding_url = f"{exchange_config.rest_url}/fapi/v1/premiumIndex?symbol={symbol}"
    funding = requests.get(funding_url).json()

    return {

        "symbol": symbol,

        "price": float(ticker["lastPrice"]),

        "change_24h": float(ticker["priceChangePercent"]),

        "funding": float(funding["lastFundingRate"]),

        "exchange": runtime_config.get("exchange","binance")

    }

@router.post("/control/mode")
def set_mode(mode: str):

    from backend.runtime.runtime_config import runtime_config

    runtime_config["mode"] = mode

    return runtime_config

@router.get("/mode")
def get_mode():

    from backend.runtime.runtime_config import runtime_config

    return {"mode": runtime_config["mode"]}
