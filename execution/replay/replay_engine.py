from dataclasses import dataclass
from typing import Optional, Dict, List

from backend.core.persistence.execution_journal import ExecutionJournal
from backend.execution.replay.deterministic_reducer import DeterministicReducer
from backend.execution.replay.execution_timeline_builder import ExecutionTimelineBuilder
from backend.execution.replay.journal_integrity_validator import JournalIntegrityValidator


@dataclass
class ReplayResult:
    freeze_flag: bool
    circuit_break_count: int
    in_flight_execution_id: Optional[str]
    last_order_id: Optional[str]


class ReplayEngine:

    def __init__(self, journal: ExecutionJournal, session_id: str):
        self.journal = journal
        self.session_id = session_id
        self.reducer = DeterministicReducer()
        self.timeline_builder = ExecutionTimelineBuilder()
        self.validator = JournalIntegrityValidator()

    def replay(self) -> ReplayResult:
        events = self.journal.load_by_session(self.session_id)

        # 1️⃣ Reducer
        state = self.reducer.rebuild(events)

        # 2️⃣ Timeline
        timeline = self.timeline_builder.build(events)

        # 3️⃣ Validator
        validation = self.validator.validate(
            events=events,
            reducer_state=state,
            timeline=timeline,
        )

        if not validation.valid:
            raise Exception(
                f"Journal integrity validation failed: "
                f"{[e.code for e in validation.fatal_errors]}"
            )

        return ReplayResult(
            freeze_flag=state.freeze_flag,
            circuit_break_count=state.circuit_consecutive_failures,
            in_flight_execution_id=state.active_execution_id,
            last_order_id=state.last_order_id,
        )
