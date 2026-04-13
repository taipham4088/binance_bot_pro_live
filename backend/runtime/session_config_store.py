"""
Per-session control panel settings (isolated from global runtime_config).

Persisted under data/sessions/<session_id>/control_config.json.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

from trading_core.config.engine_config import EngineConfig
from trading_core.data.range_trend_profiles import normalize_range_trend_engine_key

from backend.runtime.runtime_config import runtime_config

_LOCK = threading.Lock()

ALLOWED_KEYS = frozenset(
    {
        "trade_mode",
        "risk_percent",
        "initial_balance",
        "strategy",
        "symbol",
        "exchange",
    }
)


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def session_control_dir(session_id: str) -> str:
    return os.path.join(_repo_root(), "data", "sessions", session_id)


def control_config_path(session_id: str) -> str:
    return os.path.join(session_control_dir(session_id), "control_config.json")


def _defaults_from_runtime() -> Dict[str, Any]:
    return {
        "trade_mode": str(runtime_config.get("trade_mode") or "dual"),
        "risk_percent": float(runtime_config.get("risk_percent") or 0.01),
        "initial_balance": float(runtime_config.get("initial_balance") or 10000),
        "strategy": normalize_range_trend_engine_key(
            str(runtime_config.get("strategy") or "range_trend")
        ),
        "symbol": str(runtime_config.get("symbol") or "BTCUSDT"),
        "exchange": str(runtime_config.get("exchange") or "binance"),
    }


def load_control_config_merged(session_id: str) -> Dict[str, Any]:
    """Defaults from runtime_config, overridden by on-disk per-session file."""
    out = dict(_defaults_from_runtime())
    path = control_config_path(session_id)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                disk = json.load(f)
            if isinstance(disk, dict):
                for k in ALLOWED_KEYS:
                    if k in disk and disk[k] is not None:
                        out[k] = disk[k]
        except OSError as e:
            print(f"[session_config_store] read failed {path}: {e}")
        except json.JSONDecodeError as e:
            print(f"[session_config_store] invalid JSON {path}: {e}")
    out["risk_percent"] = float(out.get("risk_percent") or 0.01)
    out["initial_balance"] = float(out.get("initial_balance") or 10000)
    out["trade_mode"] = str(out.get("trade_mode") or "dual")
    out["strategy"] = normalize_range_trend_engine_key(
        str(out.get("strategy") or "range_trend")
    )
    out["symbol"] = str(out.get("symbol") or "BTCUSDT")
    out["exchange"] = str(out.get("exchange") or "binance")
    return out


def _normalize_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    if not isinstance(updates, dict):
        return clean
    for k, v in updates.items():
        if k not in ALLOWED_KEYS or v is None:
            continue
        if k in ("risk_percent", "initial_balance"):
            try:
                clean[k] = float(v)
            except (TypeError, ValueError):
                continue
        else:
            clean[k] = v
    return clean


def save_control_config_merge(session_id: str, updates: dict) -> Dict[str, Any]:
    """Merge updates onto existing file + defaults, write atomically, return full snapshot."""
    merged = load_control_config_merged(session_id)
    merged.update(_normalize_updates(updates))
    merged["strategy"] = normalize_range_trend_engine_key(
        str(merged.get("strategy") or "range_trend")
    )
    merged["risk_percent"] = float(merged.get("risk_percent") or 0.01)
    merged["initial_balance"] = float(merged.get("initial_balance") or 10000)
    d = session_control_dir(session_id)
    path = control_config_path(session_id)
    tmp = path + ".tmp"
    with _LOCK:
        os.makedirs(d, exist_ok=True)
        payload = {k: merged[k] for k in ALLOWED_KEYS if k in merged}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)
    return merged


def apply_stored_to_trading_session(session, stored: Dict[str, Any]) -> None:
    """Push stored control snapshot into session.config and risk_config (duck-typed session)."""
    rp = float(stored.get("risk_percent") or 0.01)
    c = session.config
    if isinstance(c, dict):
        c["risk_per_trade"] = rp
        c["trade_mode"] = str(stored.get("trade_mode") or "dual")
        c["initial_balance"] = float(stored.get("initial_balance") or 10000)
        c["engine"] = normalize_range_trend_engine_key(
            stored.get("strategy") or "range_trend"
        )
        c["symbol"] = str(stored.get("symbol") or "BTCUSDT")
        c["exchange"] = str(stored.get("exchange") or "binance")
    else:
        if hasattr(c, "risk_per_trade"):
            c.risk_per_trade = rp
        if hasattr(c, "trade_mode"):
            c.trade_mode = str(stored.get("trade_mode") or "dual")
        if hasattr(c, "initial_balance"):
            c.initial_balance = float(stored.get("initial_balance") or 10000)
        setattr(
            c,
            "engine",
            normalize_range_trend_engine_key(stored.get("strategy") or "range_trend"),
        )
        if hasattr(c, "symbol"):
            c.symbol = str(stored.get("symbol") or "BTCUSDT")
        if hasattr(c, "exchange"):
            c.exchange = str(stored.get("exchange") or "binance")
    if hasattr(session, "set_risk_config"):
        session.set_risk_config({"risk_per_trade": rp})


def ensure_engine_config(session) -> None:
    """Paper/Backtest services need EngineConfig-style attributes (not a plain dict)."""
    if isinstance(session.config, EngineConfig):
        return
    if not isinstance(session.config, dict):
        session.config = EngineConfig(
            initial_balance=10000.0,
            risk_per_trade=float(runtime_config.get("risk_percent", 0.01) or 0.01),
            symbol=str(runtime_config.get("symbol") or "BTCUSDT"),
            exchange=str(runtime_config.get("exchange") or "binance"),
            mode=str(getattr(session, "mode", None) or "paper"),
            trade_mode=str(runtime_config.get("trade_mode") or "dual"),
            engine=normalize_range_trend_engine_key(
                runtime_config.get("strategy") or "range_trend"
            ),
        )
        return
    d = session.config
    session.config = EngineConfig(
        initial_balance=float(d.get("initial_balance", 10000)),
        risk_per_trade=float(
            d.get("risk_per_trade", runtime_config.get("risk_percent", 0.01) or 0.01)
        ),
        symbol=str(d.get("symbol") or runtime_config.get("symbol") or "BTCUSDT"),
        exchange=str(d.get("exchange") or runtime_config.get("exchange") or "binance"),
        mode=str(d.get("mode") or getattr(session, "mode", None) or "paper"),
        trade_mode=str(d.get("trade_mode") or runtime_config.get("trade_mode") or "dual"),
        engine=normalize_range_trend_engine_key(
            d.get("engine")
            or d.get("strategy")
            or runtime_config.get("strategy")
            or "range_trend"
        ),
    )
