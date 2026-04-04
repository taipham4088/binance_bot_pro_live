import pandas as pd

def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df["time"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("time").reset_index(drop=True)
    return df
