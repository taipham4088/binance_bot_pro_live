def build_h1(df):
    df_1h = df.set_index('time').resample('1h').agg({
        'open':'first',
        'high':'max',
        'low':'min',
        'close':'last',
        'volume':'sum'
    }).dropna().reset_index()

    return df_1h
