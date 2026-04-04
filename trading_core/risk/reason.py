from enum import Enum


class RiskReason(str, Enum):
    DAILY_STOP = "DAILY_STOP"
    DAILY_DD_BLOCK = "DAILY_DD_BLOCK"
    MANUAL_FREEZE = "MANUAL_FREEZE"
    SYSTEM_RISK = "SYSTEM_RISK"
