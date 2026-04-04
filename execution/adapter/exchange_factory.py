import os
from execution.adapter.binance.binance_adapter import BinanceExecutionAdapter


def create_exchange_adapter(
    config: dict,
    sync_engine,
    execution_state,
    execution_lock
):
    exchange_name = getattr(config, "exchange", "binance").lower()
    print(f"[ExchangeFactory] Creating adapter: {exchange_name}")

    if exchange_name == "binance":

        return BinanceExecutionAdapter(
            api_key=os.getenv("BINANCE_API_KEY"),
            api_secret=os.getenv("BINANCE_API_SECRET"),
            sync_engine=sync_engine,
            execution_state=execution_state,
            execution_lock=execution_lock,
            symbol=config.symbol
        )

    raise ValueError(f"Unsupported exchange: {exchange_name}")
