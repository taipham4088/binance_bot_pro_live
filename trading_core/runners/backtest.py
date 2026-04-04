from trading_core.runtime.context import RuntimeContext
from trading_core.engines.dual_engine import DualEngine
from trading_core.results.backtest_result import BacktestResult

from trading_core.data.loader import load_csv
from trading_core.data.resampler import build_h1
from trading_core.data.feature_builder import build_features


def prepare_data(csv_path: str):
    df = load_csv(csv_path)
    df_1h = build_h1(df)
    df = build_features(df, df_1h)
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
