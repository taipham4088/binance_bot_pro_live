from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionPlan:
    plan: str            # NOOP | OPEN_POSITION | REDUCE_ONLY | CLOSE_POSITION | BLOCK
    reason: str
    source: str
    timestamp: int
