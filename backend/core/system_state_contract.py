# backend/core/system_state_contract.py

import time
from copy import deepcopy


# =========================================================
# SYSTEM STATE CONTRACT v1
# =========================================================

SYSTEM_STATE_VERSION = "1.0.0"


# =========================================================
# ENVELOPE
# =========================================================

def empty_envelope(session_id: str, mode: str = "SNAPSHOT") -> dict:
    return {
        "type": "SYSTEM_STATE",
        "version": SYSTEM_STATE_VERSION,
        "mode": mode,                 # SNAPSHOT | DELTA
        "session_id": session_id,
        "ts": int(time.time() * 1000),

        "system": empty_system(),
        "execution": empty_execution(),
        "risk": empty_risk(),
        "account": empty_account(),
        "analytics": empty_analytics(),
        "health": empty_health(),
    }


# =========================================================
# BLOCKS (CONTRACT DOMAINS)
# =========================================================

def empty_system() -> dict:
    return {
        "state": "CREATED",      # CREATED | READY | LIVE | FROZEN | STOPPED | ERROR
        "mode": None,            # LIVE | PAPER | BACKTEST
        "session_id": None,

        "uptime": 0,
        "started_at": None,

        "last_event": None,
        "last_error": None,
        "flags": []
    }


def empty_execution() -> dict:
    return {
        "state": "IDLE",     # IDLE | SYNCING | RUNNING | ERROR

        "position": {
            "net": 0.0,
            "long": 0.0,
            "short": 0.0,
            "side": "FLAT",        # LONG | SHORT | FLAT
            "symbol": None,
            "entry_price": None,
            "unrealized_pnl": 0.0
        },

        "orders": {
            "open": 0,
            "pending_intents": 0,
            "last_action": None,
            "last_order_id": None
        },

        "transition": {
            "last_type": None,    # OPEN | CLOSE | REVERSE | ADJUST
            "last_ts": None
        },

        "sync": {
            "drift": False,
            "last_reconcile": None
        },

        "last_update": None,
        "flags": []
    }


def empty_risk() -> dict:
    return {
        "frozen": False,
        "freeze_reason": None,

        "daily": {
            "pnl": 0.0,
            "drawdown": 0.0,
            "trades": 0
        },

        "limits": {
            "max_daily_dd": None,
            "max_trades": None,
            "max_exposure": None
        },

        "last_event": None,
        "last_update": None,
        "flags": []
    }


def empty_account() -> dict:
    return {
        "equity": 0.0,
        "balance": 0.0,
        "available": 0.0,
        "margin_used": 0.0,

        "unrealized_pnl": 0.0,
        "realized_pnl": 0.0,
        "drawdown": 0.0,

        "last_update": None
    }


def empty_analytics() -> dict:
    return {
        "equity_state": "NEUTRAL",
        "side_bias": "NONE",
        "regime": None,
        "confidence": None,

        "last_update": None
    }


def empty_health() -> dict:
    return {
        "alive": True,

        "components": {
            "execution": "UNKNOWN",
            "risk": "UNKNOWN",
            "exchange_ws": "UNKNOWN",
            "exchange_rest": "UNKNOWN",
            "state_engine": "UNKNOWN"
        },

        "latency": {
            "ws_ms": None,
            "order_ms": None,
            "state_ms": None
        },

        "event_rate": {
            "execution": 0.0,
            "risk": 0.0,
            "account": 0.0
        },

        "last_heartbeat": None,
        "warnings": []
    }


# =========================================================
# HELPERS
# =========================================================

def new_snapshot(session_id: str) -> dict:
    return empty_envelope(session_id=session_id, mode="SNAPSHOT")


def new_delta(session_id: str, patch: dict, seq: int, ts: int) -> dict:
    """
    patch: { block_name: block_value }
    """
    ops = []

    for block_name, block_value in patch.items():
        ops.append({
            "op": "replace",
            "path": f"/{block_name}",
            "value": block_value
        })

    return {
        "type": "SYSTEM_STATE",
        "version": SYSTEM_STATE_VERSION,
        "mode": "DELTA",
        "session_id": session_id,
        "seq": seq,
        "ts": ts,
        "patch": ops          # 👈 JSON Patch LIST
    }


def deep_clone(state: dict) -> dict:
    return deepcopy(state)
