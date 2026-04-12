"""
Standalone Binance USD-M Futures kline downloader (read-only, mainnet).

Writes CSV to data/import/ for manual use in backtests. Not wired into any engine.

Timestamp is UTC: open time is parsed from exchange milliseconds as UTC, then written as
naive ``YYYY-MM-DD HH:MM:SS`` strings (UTC wall time) so backtests treat rows consistently
regardless of local timezone.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

FAPI_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
MAX_LIMIT = 1500
REQUEST_SLEEP_SEC = 0.2

SUPPORTED_INTERVALS = frozenset(
    {"1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"}
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_utc_day_start(date_str: str) -> datetime:
    """Parse YYYY-MM-DD as 00:00:00 UTC."""
    dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _year_suffix(start_dt: datetime, end_dt: datetime) -> str:
    if start_dt.year == end_dt.year:
        return str(start_dt.year)
    return f"{start_dt.year}_{end_dt.year}"


def download_binance_data(
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str,
    *,
    out_dir: Path | str | None = None,
) -> Path:
    """
    Download historical futures klines from Binance mainnet and save CSV.

    ``end_date`` is exclusive (same idea as range stop): candles with open time
    strictly before 00:00:00 UTC on ``end_date`` are included.

    Output matches standard backtest CSV import: ``timestamp`` (naive UTC wall time as
    ``%Y-%m-%d %H:%M:%S``), ``open``, ``high``, ``low``, ``close``, ``volume`` — Binance
    extra fields are dropped.
    """
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(
            f"interval must be one of {sorted(SUPPORTED_INTERVALS)}, got {interval!r}"
        )

    sym = symbol.strip().upper()
    start_dt = _parse_utc_day_start(start_date)
    end_dt = _parse_utc_day_start(end_date)
    if end_dt <= start_dt:
        raise ValueError("end_date must be after start_date")

    start_ms = _ms(start_dt)
    end_ms_exclusive = _ms(end_dt)

    root = _repo_root()
    dest = Path(out_dir) if out_dir is not None else root / "data" / "import"
    dest.mkdir(parents=True, exist_ok=True)

    fname = f"binance_futures_{sym}_{interval}_{_year_suffix(start_dt, end_dt)}.csv"
    out_path = dest / fname

    print("Downloading (futures)...")
    rows: list[list] = []
    current = start_ms
    end_time_param = end_ms_exclusive - 1

    while current < end_ms_exclusive:
        params = {
            "symbol": sym,
            "interval": interval,
            "startTime": current,
            "endTime": end_time_param,
            "limit": MAX_LIMIT,
        }
        resp = requests.get(FAPI_KLINES_URL, params=params, timeout=60)
        resp.raise_for_status()
        batch = resp.json()

        if not batch:
            break

        for k in batch:
            open_t = int(k[0])
            if open_t < start_ms or open_t >= end_ms_exclusive:
                continue
            rows.append(k)

        last_open = int(batch[-1][0])
        next_start = last_open + 1
        if next_start <= current:
            break
        current = next_start

        print(f"Fetched {len(rows)} candles")

        time.sleep(REQUEST_SLEEP_SEC)

        if len(batch) < MAX_LIMIT:
            break

    if not rows:
        raise RuntimeError("No candles returned; check symbol, interval, and date range.")

    # De-duplicate by open time (ms), preserve order
    seen: set[int] = set()
    unique: list[list] = []
    for k in rows:
        ot = int(k[0])
        if ot in seen:
            continue
        seen.add(ot)
        unique.append(k)
    unique.sort(key=lambda x: int(x[0]))

    open_times = [int(k[0]) for k in unique]
    df = pd.DataFrame(
        {
            "open": [float(k[1]) for k in unique],
            "high": [float(k[2]) for k in unique],
            "low": [float(k[3]) for k in unique],
            "close": [float(k[4]) for k in unique],
            "volume": [float(k[5]) for k in unique],
        }
    )
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)

    # UTC open time → naive UTC datetime (timezone-safe for backtest CSV import)
    ts = pd.to_datetime(open_times, unit="ms", utc=True).tz_convert(None)
    df["timestamp"] = ts.strftime("%Y-%m-%d %H:%M:%S")

    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")
    return out_path


if __name__ == "__main__":
    symbol = "BTCUSDT"
    interval = "5m"
    start_date = "2024-01-01"
    end_date = "2025-01-01"

    path = download_binance_data(symbol, interval, start_date, end_date)
    print(path.name)
