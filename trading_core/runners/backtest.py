from trading_core.runtime.context import RuntimeContext
from trading_core.engines.dual_engine import DualEngine
from trading_core.results.backtest_result import BacktestResult

from trading_core.data.loader import load_csv
from trading_core.data.resampler import resample_ohlc_from_entry
from trading_core.data.feature_builder import build_features
from trading_core.data.range_trend_profiles import range_trend_entry_regime_intervals


def prepare_data(csv_path: str, engine_key: str | None = None):
    """CSV rows must be at the strategy entry timeframe (e.g. 5m bars for range_trend)."""
    df = load_csv(csv_path)
    _, reg_iv = range_trend_entry_regime_intervals(engine_key or "range_trend")
    df_regime = resample_ohlc_from_entry(df, reg_iv, drop_last_incomplete=True)
    df = build_features(df, df_regime, regime_interval=reg_iv)
    return df


def run_backtest(config, df):

    context = RuntimeContext(config)
    engine = DualEngine(config, context)

    for i in range(80, len(df)):
        engine.on_bar(i, df.iloc[i], df)

    return BacktestResult(
        trades=engine.trades,
        equity_curve=engine.equity_tracker.curve,
        stats={}
    )
