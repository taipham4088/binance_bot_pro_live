import requests
import pandas as pd
from backend.runtime.exchange_config import exchange_config

BASE_URL = exchange_config.get_klines_url()


class BinanceHistoryLoader:

    @staticmethod
    def load(symbol, interval, limit):

        all_rows = []
        end_time = None

        while len(all_rows) < limit:

            fetch = min(1500, limit - len(all_rows))

            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": fetch
            }

            if end_time:
                params["endTime"] = end_time

            resp = requests.get(BASE_URL, params=params)
            resp.raise_for_status()

            data = resp.json()

            if not data:
                break

            all_rows = data + all_rows

            end_time = data[0][0] - 1

        df = pd.DataFrame(all_rows, columns=[
            "time","open","high","low","close","volume",
            "_","_","_","_","_","_"
        ])

        df = df[["time","open","high","low","close","volume"]]

        df["time"] = pd.to_datetime(df["time"], unit="ms")

        for c in ["open","high","low","close","volume"]:
            df[c] = df[c].astype(float)

        return df