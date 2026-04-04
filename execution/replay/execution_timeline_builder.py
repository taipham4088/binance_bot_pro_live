# execution/replay/execution_timeline_builder.py

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class StepTimeline:
    step: Optional[str]
    side: Optional[str]
    quantity: Optional[float]
    order_id: Optional[str]
    status: Optional[str]
    ts: int


@dataclass
class ExecutionTimeline:
    execution_id: str
    steps: List[StepTimeline] = field(default_factory=list)
    finalized: bool = False
    final_event: Optional[str] = None
    freeze_snapshot: bool = False


class ExecutionTimelineBuilder:
    """
    Builds deterministic execution timeline from journal.
    Pure function. No side effects.
    """

    def build(self, events: List[Dict[str, Any]]) -> List[ExecutionTimeline]:
        executions: Dict[str, ExecutionTimeline] = {}

        for event in events:
            execution_id = event.get("execution_id")
            if not execution_id:
                continue

            if execution_id not in executions:
                executions[execution_id] = ExecutionTimeline(
                    execution_id=execution_id
                )

            timeline = executions[execution_id]

            event_type = event.get("event_type")

            if event_type == "STEP_SENT":
                timeline.steps.append(
                    StepTimeline(
                        step=event.get("step"),
                        side=event.get("side"),
                        quantity=event.get("quantity"),
                        order_id=event.get("order_id"),
                        status="SENT",
                        ts=event.get("ts"),
                    )
                )

            if event_type in ("EXECUTION_COMPLETED", "EXECUTION_FAILED"):
                timeline.finalized = True
                timeline.final_event = event_type

            if event_type == "SYSTEM_FROZEN":
                timeline.freeze_snapshot = True

        return list(executions.values())
