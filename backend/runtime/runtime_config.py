"""
Process-wide control panel settings (symbol, strategy, pause, etc.).

Persisted to data/runtime_config.json (repo data/ is typically gitignored).
Loaded on first import so values exist before dashboard and analytics use them.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

_SAVE_LOCK = threading.Lock()

# Keys written to disk (single source for control API + dashboard config).
PERSISTED_KEYS = (
    "trading_enabled",
    "exchange",
    "symbol",
    "mode",
    "risk_percent",
    "trade_mode",
    "strategy",
)

_DEFAULTS: Dict[str, Any] = {
    "trading_enabled": True,
    "exchange": "binance",
    "symbol": "BTCUSDT",
    "mode": "shadow",
    "risk_percent": 0.01,
    "trade_mode": "both",
    "strategy": "dual_engine",
}


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def runtime_config_path() -> str:
    return os.path.join(_repo_root(), "data", "runtime_config.json")


def _coerce(key: str, value: Any) -> Any:
    if key == "trading_enabled":
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if key == "risk_percent":
        try:
            return float(value)
        except (TypeError, ValueError):
            return _DEFAULTS["risk_percent"]
    if value is None:
        return _DEFAULTS[key]
    return value


def _load_file_into(target: Dict[str, Any]) -> None:
    path = runtime_config_path()
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[runtime_config] could not load {path}: {e}")
        return
    if not isinstance(raw, dict):
        return
    # Human-friendly alias: "paused": true -> trading_enabled false
    if "paused" in raw and "trading_enabled" not in raw:
        raw = {**raw, "trading_enabled": not bool(raw.get("paused"))}
    for key in PERSISTED_KEYS:
        if key not in raw:
            continue
        target[key] = _coerce(key, raw[key])
    # Older JSON files may omit exchange; coerce can leave empty string
    if not target.get("exchange"):
        target["exchange"] = _DEFAULTS["exchange"]


def save_runtime_config() -> None:
    """Atomically persist current control panel settings."""
    path = runtime_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {k: runtime_config[k] for k in PERSISTED_KEYS}
    tmp = path + ".tmp"
    with _SAVE_LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)


def reload_runtime_config_from_disk() -> None:
    """Re-read file into the live dict (same object references stay valid)."""
    for k, v in _DEFAULTS.items():
        runtime_config[k] = v
    _load_file_into(runtime_config)


runtime_config: Dict[str, Any] = dict(_DEFAULTS)
_load_file_into(runtime_config)
