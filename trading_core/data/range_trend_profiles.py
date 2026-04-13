"""
Range Trend variants: same DualEngine logic, different entry vs regime (filter) timeframes.

Binance kline interval strings (REST/WS) map to pandas resample frequencies.
"""

from __future__ import annotations

import pandas as pd

# Binance USDT-M kline intervals used by this project
BINANCE_INTERVAL_TO_PANDAS_FREQ: dict[str, str] = {
    "1m": "1min",
    "3m": "3min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1D",
}

_LEGACY_ENGINE = frozenset({"range", "trend", "momentum", "dual_engine"})

# engine registry key -> (entry_interval, regime_interval)
RANGE_TREND_PROFILES: dict[str, tuple[str, str]] = {
    "range_trend": ("5m", "1h"),
    "range_trend_1m": ("1m", "15m"),
    "range_trend_15m": ("15m", "4h"),
    "range_trend_1h": ("1h", "12h"),
}


def normalize_range_trend_engine_key(name: str | None) -> str:
    n = (name or "range_trend").strip().lower()
    if n in _LEGACY_ENGINE:
        return "range_trend"
    if n in RANGE_TREND_PROFILES:
        return n
    return "range_trend"


def range_trend_entry_regime_intervals(engine_key: str | None) -> tuple[str, str]:
    k = normalize_range_trend_engine_key(engine_key)
    return RANGE_TREND_PROFILES[k]


def pandas_freq_for_binance_interval(interval: str) -> str:
    i = (interval or "5m").strip().lower()
    return BINANCE_INTERVAL_TO_PANDAS_FREQ.get(i, "5min")


def merge_tolerance_for_regime_interval(regime_interval: str) -> pd.Timedelta:
    """merge_asof backward tolerance: one full regime bar + epsilon."""
    freq = pandas_freq_for_binance_interval(regime_interval)
    base = pd.to_timedelta(freq)
    return base + pd.Timedelta(seconds=1)
