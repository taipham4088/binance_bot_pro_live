# =====================================================================
# ⚠ LEGACY DECISION ENGINE – NOT USED IN PRODUCTION FLOW
#
# This module belongs to the old execution decision engine.
# The current production architecture uses:
#   - backend/core/*
#   - execution/live_execution_system.py
#
# DO NOT import this module into backend/core or WS flow.
# =====================================================================
from enum import Enum


class Authority(str, Enum):
    PAPER = "paper"
    LIVE_READONLY = "live-readonly"
    LIVE_TRADE = "live-trade"


class ExecutionPlanType(str, Enum):
    NOOP = "NOOP"
    OPEN_POSITION = "OPEN_POSITION"
    REDUCE_ONLY = "REDUCE_ONLY"
    CLOSE_POSITION = "CLOSE_POSITION"
    BLOCK = "BLOCK"


class HealthState(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    CRITICAL = "critical"
