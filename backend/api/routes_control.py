from fastapi import APIRouter, Body, Request

from backend.core.session_runtime import (
    sync_dashboard_risk_to_all_sessions,
    sync_dashboard_symbol_to_all_sessions,
)
from backend.runtime.runtime_config import runtime_config, save_runtime_config
from backend.runtime.exchange_config import exchange_config

router = APIRouter()

@router.post("/control/pause")
def pause_bot():
    runtime_config["trading_enabled"] = False
    save_runtime_config()
    return {"status": "paused"}

@router.post("/control/resume")
def resume_bot():
    runtime_config["trading_enabled"] = True
    save_runtime_config()
    return {"status": "running"}

@router.post("/control/risk")
def set_risk(request: Request, data: dict = Body(...)):
    runtime_config["risk_percent"] = data.get("risk")
    save_runtime_config()
    sync_dashboard_risk_to_all_sessions(getattr(request.app.state, "manager", None))
    return runtime_config

@router.post("/control/trade_mode")
def set_trade_mode(data: dict = Body(...)):
    runtime_config["trade_mode"] = data.get("mode")
    save_runtime_config()
    return runtime_config

@router.post("/control/strategy")
def set_strategy(data: dict = Body(...)):
    runtime_config["strategy"] = data.get("strategy")
    save_runtime_config()
    return runtime_config

@router.post("/control/exchange")
def set_exchange(data: dict = Body(...)):
    runtime_config["exchange"] = data.get("exchange")
    save_runtime_config()
    return runtime_config

@router.post("/control/symbol")
def set_symbol(request: Request, data: dict = Body(...)):
    runtime_config["symbol"] = data.get("symbol")
    save_runtime_config()
    results = sync_dashboard_symbol_to_all_sessions(
        getattr(request.app.state, "manager", None),
        symbol=runtime_config.get("symbol"),
    )
    return {**runtime_config, "sessions": results}


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
def set_mode(data: dict = Body(...)):
    runtime_config["mode"] = data.get("mode")
    save_runtime_config()
    return runtime_config

@router.get("/mode")
def get_mode():

    return {"mode": runtime_config["mode"]}
