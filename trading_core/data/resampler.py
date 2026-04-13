import pandas as pd

from trading_core.data.range_trend_profiles import pandas_freq_for_binance_interval

try:
    from backend.runtime.runtime_config import runtime_config as _runtime_config
except Exception:
    _runtime_config = {}


def resample_ohlc_from_entry(
    df: pd.DataFrame,
    binance_interval: str,
    *,
    drop_last_incomplete: bool = True,
) -> pd.DataFrame:
    """
    Aggregate entry-timeframe OHLCV bars into a higher timeframe (regime bars).
    Matches live pipeline: optional drop of the last (still-forming) entry candle before resampling.
    """
    out = df.copy()
    out["time"] = pd.to_datetime(out["time"])
    out = out.sort_values("time")
    if drop_last_incomplete and len(out) > 1:
        out = out.iloc[:-1]
    freq = pandas_freq_for_binance_interval(binance_interval)
    agg = (
        out.set_index("time")
        .resample(freq)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
        .reset_index()
    )
    return agg


def _get_reference_timeframe() -> str:
    tf = (_runtime_config or {}).get("test_timeframe")
    if isinstance(tf, str) and tf.strip():
        return tf.strip().lower()
    return "5m"


def build_reference_tf(df):
    timeframe = _get_reference_timeframe()
    return df.set_index("time").resample(timeframe).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna().reset_index()


def build_h1(df):
    return resample_ohlc_from_entry(df, "1h", drop_last_incomplete=True)
