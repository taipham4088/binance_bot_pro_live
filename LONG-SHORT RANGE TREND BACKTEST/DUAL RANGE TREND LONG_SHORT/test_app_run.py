from trading_core.config.engine_config import EngineConfig
from trading_core.runners.backtest import prepare_data, run_backtest

config = EngineConfig(
    initial_balance=10000,
    risk_per_trade=0.01,
    daily_stop_losses=2,
    daily_dd_limit=0.03,
    core_mode="locked",
    trade_mode="dual"
)

df = prepare_data("futures_BTCUSDT_5m_FULL.csv")
result = run_backtest(config, df)

trades = result.trades
equity = result.equity_curve
