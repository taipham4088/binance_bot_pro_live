try:
    from backend.runtime.runtime_config import runtime_config as _runtime_config
except Exception:
    _runtime_config = {}


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
    df_1h = df.set_index('time').resample('1h').agg({
        'open':'first',
        'high':'max',
        'low':'min',
        'close':'last',
        'volume':'sum'
    }).dropna().reset_index()

    return df_1h
