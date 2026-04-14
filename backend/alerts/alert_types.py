from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertSource(str, Enum):
    EXECUTION = "execution"
    SYSTEM = "system"
    ADAPTER = "adapter"
    EXCHANGE = "exchange"
    MONITORING = "monitoring"


@dataclass(frozen=True)
class Alert:
    level: AlertLevel | str
    source: AlertSource | str
    message: str
    session: Optional[str] = None
    symbol: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    metadata: Optional[Mapping[str, Any]] = None
