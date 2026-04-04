from dataclasses import dataclass
from typing import Any


@dataclass
class TimelineEvent:
    index: int
    input: Any
    decision: Any
    timestamp: int
