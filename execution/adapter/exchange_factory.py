import os
from typing import Any, Mapping

from execution.adapter.binance.binance_adapter import BinanceExecutionAdapter
from backend.runtime.runtime_config import runtime_config


def _cfg_get(config: Any, key: str, default=None):
    if isinstance(config, Mapping):
        v = config.get(key)
        if v is None or v == "":
            return default
        return v
    v = getattr(config, key, default)
    if v is None or v == "":
        return default
    return v


def create_exchange_adapter(
    config: dict,
    sync_engine,
    execution_state,
    execution_lock
):
    # runtime_config is control-panel source of truth; session config may be dict or EngineConfig.
    exchange_name = (
        runtime_config.get("exchange")
        or _cfg_get(config, "exchange", "binance")
        or "binance"
    )
    exchange_name = str(exchange_name).lower()
    print(f"[ExchangeFactory] Creating adapter: {exchange_name}")

    symbol = (
        runtime_config.get("symbol")
        or _cfg_get(config, "symbol", "BTCUSDT")
        or "BTCUSDT"
    )

    if exchange_name == "binance":

        return BinanceExecutionAdapter(
            api_key=os.getenv("BINANCE_API_KEY"),
            api_secret=os.getenv("BINANCE_API_SECRET"),
            sync_engine=sync_engine,
            execution_state=execution_state,
            execution_lock=execution_lock,
            symbol=symbol
        )

    raise ValueError(f"Unsupported exchange: {exchange_name}")
