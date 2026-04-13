import math

from fastapi import APIRouter, Body, HTTPException, Query, Request

from backend.core.session_runtime import (
    sync_dashboard_risk_to_all_sessions,
    sync_dashboard_symbol_to_all_sessions,
)
from backend.core.trading_session import canonical_session_id
from backend.runtime.runtime_config import runtime_config, save_runtime_config
from backend.runtime.session_config_store import (
    apply_stored_to_trading_session,
    save_control_config_merge,
)

_LEGACY_STRATEGY = frozenset({"range", "trend", "momentum", "dual_engine"})
_ALLOWED_STRATEGY = frozenset(
    {
        "range_trend",
        "range_trend_1m",
        "range_trend_15m",
        "range_trend_1h",
    }
)


def _normalize_persisted_strategy(value) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "range_trend"
    n = str(value).strip().lower()
    if n in _LEGACY_STRATEGY:
        return "range_trend"
    if n in _ALLOWED_STRATEGY:
        return n
    return "range_trend"


def _normalize_trade_mode(value) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "dual"
    n = str(value).strip().lower()
    if n == "both":
        return "dual"
    if n in ("long", "short", "dual"):
        return n
    return "dual"
from backend.runtime.exchange_config import exchange_config

router = APIRouter()


def _coerce_positive_risk_fraction(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or x <= 0:
        return None
    return x


def _apply_control_to_session(request: Request, session: str, updates: dict) -> dict:
    sid = canonical_session_id(session)
    merged = save_control_config_merge(sid, updates)
    mgr = getattr(request.app.state, "manager", None)
    sess = mgr.get(sid) if mgr else None
    if sess:
        ensure_engine_config(sess)
        apply_stored_to_trading_session(sess, merged)
    return {"session_id": sid, **merged}


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
def set_risk(
    request: Request,
    data: dict = Body(...),
    session: str | None = Query(
        None,
        description="When set, update only this session (file + live object); omit for legacy global sync",
    ),
):
    rp = _coerce_positive_risk_fraction(data.get("risk"))
    if rp is None:
        raise HTTPException(status_code=400, detail="risk must be a positive finite number (fraction, e.g. 0.01 = 1%)")
    if session and str(session).strip():
        out = _apply_control_to_session(request, session, {"risk_percent": rp})
        return {**out, "risk_percent": rp}
    runtime_config["risk_percent"] = rp
    save_runtime_config()
    sync_dashboard_risk_to_all_sessions(getattr(request.app.state, "manager", None))
    return runtime_config

@router.post("/control/trade_mode")
def set_trade_mode(
    request: Request,
    data: dict = Body(...),
    session: str | None = Query(None),
):
    mode_norm = _normalize_trade_mode(data.get("mode"))
    if session and str(session).strip():
        return _apply_control_to_session(request, session, {"trade_mode": mode_norm})
    runtime_config["trade_mode"] = mode_norm
    save_runtime_config()
    return runtime_config

@router.post("/control/strategy")
def set_strategy(
    request: Request,
    data: dict = Body(...),
    session: str | None = Query(None),
):
    strat = _normalize_persisted_strategy(data.get("strategy"))
    if session and str(session).strip():
        return _apply_control_to_session(request, session, {"strategy": strat})
    runtime_config["strategy"] = strat
    save_runtime_config()
    return runtime_config

@router.post("/control/exchange")
def set_exchange(
    request: Request,
    data: dict = Body(...),
    session: str | None = Query(None),
):
    ex = data.get("exchange")
    if ex is None or str(ex).strip() == "":
        raise HTTPException(status_code=400, detail="exchange is required")
    if session and str(session).strip():
        return _apply_control_to_session(request, session, {"exchange": str(ex).strip()})
    runtime_config["exchange"] = ex
    save_runtime_config()
    return runtime_config

@router.post("/control/symbol")
def set_symbol(
    request: Request,
    data: dict = Body(...),
    session: str | None = Query(None),
):
    sym = data.get("symbol")
    if sym is None or str(sym).strip() == "":
        raise HTTPException(status_code=400, detail="symbol is required")
    sym_s = str(sym).strip().upper()
    if session and str(session).strip():
        out = _apply_control_to_session(request, session, {"symbol": sym_s})
        mgr = getattr(request.app.state, "manager", None)
        sess = mgr.get(out["session_id"]) if mgr else None
        sym_result = None
        if sess:
            sym_result = sess.request_symbol_change(sym_s)
        return {**out, "symbol": sym_s, "symbol_change": sym_result}
    runtime_config["symbol"] = sym_s
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
