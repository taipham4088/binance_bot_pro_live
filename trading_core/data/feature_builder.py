import pandas as pd

def build_features(df, df_1h,
                   h1_range_lookback=30,
                   h1_max_trade_bars=5):

    df = df.copy()
    # ===== REMOVE OLD H1 FEATURE COLUMNS =====
    drop_cols = [
        "ema200",
        "close_1h",
        "valid_long",
        "valid_short",
        "range_high",
        "range_low"
    ]

    for c in drop_cols:
        if c in df.columns:
            df = df.drop(columns=c)

    df_1h = df_1h.copy()

    df_1h = df_1h.sort_values("time").reset_index(drop=True)

    # ===== H1 FEATURES =====

    df_1h['ema200'] = df_1h['close'].ewm(span=200, adjust=False).mean()

    df_1h['range_high'] = df_1h['high'].rolling(h1_range_lookback).max()
    df_1h['range_low']  = df_1h['low'].rolling(h1_range_lookback).min()

    # LONG regime
    df_1h['break_up'] = df_1h['close'] > df_1h['range_high'].shift(1)
    df_1h['break_up_id'] = (
        df_1h['break_up']
        & ~df_1h['break_up'].shift(1, fill_value=False)
    ).cumsum()
    df_1h['bars_since_break_up'] = df_1h.groupby('break_up_id').cumcount()

    df_1h['valid_long'] = (
        (df_1h['break_up_id'] > 0) &
        (df_1h['bars_since_break_up'] <= h1_max_trade_bars) &
        (df_1h['close'] > df_1h['range_low'])
    )

    # SHORT regime
    df_1h['break_down'] = df_1h['close'] < df_1h['range_low'].shift(1)
    df_1h['break_down_id'] = (
        df_1h['break_down']
        & ~df_1h['break_down'].shift(1, fill_value=False)
    ).cumsum()
    df_1h['bars_since_break_down'] = df_1h.groupby('break_down_id').cumcount()

    df_1h['valid_short'] = (
        (df_1h['break_down_id'] > 0) &
        (df_1h['bars_since_break_down'] <= h1_max_trade_bars) &
        (df_1h['close'] < df_1h['range_high'])
    )

    # ===== LIVE-SAFE COLUMN GUARD =====

    required_h1 = [
        'time',
        'ema200',
        'close',
        'valid_long',
        'valid_short',
        'range_high',
        'range_low'
    ]

    df_h1_safe = df_1h.copy()

    for col in required_h1:
        if col not in df_h1_safe.columns:
            df_h1_safe[col] = None

    df_h1_safe = df_h1_safe.rename(columns={'close': 'close_1h'})

    df_h1_safe = df_h1_safe[
        ['time','ema200','close_1h','valid_long','valid_short','range_high','range_low']
    ]

    df_h1_safe = df_h1_safe.ffill()
    # ===== MERGE =====

    df["time"] = pd.to_datetime(df["time"])
    df_h1_safe["time"] = pd.to_datetime(df_h1_safe["time"])

    df = df.sort_values("time").reset_index(drop=True)
    df_h1_safe = df_h1_safe.sort_values("time").reset_index(drop=True)

    df_h1_safe = df_h1_safe.drop_duplicates("time")
    
    df_merge = pd.merge_asof(
        df,
        df_h1_safe,
        on="time",
        direction="backward",
        allow_exact_matches=True,
        tolerance=pd.Timedelta("1h")
    )
    # ===== LIVE-SAFE FFILL =====

    required_merge = [
        'ema200',
        'close_1h',
        'valid_long',
        'valid_short',
        'range_high',
        'range_low'
    ]

    for col in required_merge:
        if col not in df_merge.columns:
            df_merge[col] = pd.NA
           
    cols = ["time","ema200","close_1h"]
    cols = [c for c in cols if c in df_merge.columns]
                 
    # forward fill context H1
    df_merge[required_merge] = df_merge[required_merge].ffill()

    return df_merge
