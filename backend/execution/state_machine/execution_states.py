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
class ExecutionStates:
    IDLE = "IDLE"
    OPENING = "OPENING"
    OPEN = "OPEN"
    REDUCING = "REDUCING"
    CLOSING = "CLOSING"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
