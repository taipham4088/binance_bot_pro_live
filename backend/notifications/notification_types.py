from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class NotificationType:
    ALERT = "ALERT"
    POSITION_OPEN = "POSITION_OPEN"
    POSITION_CLOSE = "POSITION_CLOSE"
    POSITION_REVERSE = "POSITION_REVERSE"


@dataclass
class Notification:
    type: str
    message: str
    level: str
    source: str
    session: Optional[str] = None
    symbol: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)
