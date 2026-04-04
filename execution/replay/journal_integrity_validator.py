# execution/replay/journal_integrity_validator.py

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Set


# ===============================
# Validation Models
# ===============================

@dataclass
class ValidationError:
    code: str
    execution_id: Optional[str]
    message: str


@dataclass
class ValidationResult:
    valid: bool
    fatal_errors: List[ValidationError]
    warnings: List[ValidationError]


# ===============================
# Journal Integrity Validator
# ===============================

class JournalIntegrityValidator:

    CIRCUIT_THRESHOLD = 3

    TERMINAL_STEP_EVENTS = {
        "STEP_FILLED",
        "STEP_FAILED",
        "STEP_CANCELLED",
    }

    FINALIZATION_EVENTS = {
        "EXECUTION_COMPLETED",
        "EXECUTION_ABORTED",
    }

    FREEZE_EVENTS = {
        "SYSTEM_FROZEN",
        "SYSTEM_UNFROZEN",
    }

    ALLOWED_EVENT_TYPES = {

        # execution lifecycle
        "INTENT_RECEIVED",
        "EXECUTION_STARTED",
        "EXECUTION_COMPLETED",
        "EXECUTION_FAILED",
        "EXECUTION_ABORTED",

        # step lifecycle (real production)
        "STEP_CLOSE_SENT",
        "STEP_OPEN_SENT",
        "STEP_CLOSE_CONFIRMED",
        "STEP_OPEN_CONFIRMED",

        # legacy compatibility
        "STEP_SENT",
        "STEP_FILLED",
        "STEP_FAILED",
        "STEP_CANCELLED",

        # circuit breaker
        "CIRCUIT_BREAK_INCREMENT",
        "CIRCUIT_RESET",

        # freeze
        "SYSTEM_FROZEN",
        "SYSTEM_UNFROZEN",
    }

    # ==========================================
    # Public API
    # ==========================================

    def validate(
        self,
        events: List[Any],
        reducer_state: Any,
        timeline: List[Any],
    ) -> ValidationResult:

        fatal_errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        if not events:
            return ValidationResult(True, [], [])

        # ==========================
        # S1 — Strict Monotonic Order
        # ==========================
        last_id = None
        seen_ids: Set[int] = set()

        for event in events:
            event_id = event.get("id")

            if event_id in seen_ids:
                fatal_errors.append(
                    ValidationError(
                        "DUPLICATE_EVENT_ID",
                        event.get("execution_id"),
                        f"Duplicate event id detected: {event_id}",
                    )
                )

            seen_ids.add(event_id)

            if last_id is not None and event_id <= last_id:
                fatal_errors.append(
                    ValidationError(
                        "INVALID_EVENT_ORDER",
                        event.get("execution_id"),
                        "Events are not strictly increasing by id",
                    )
                )

            last_id = event_id

        # ==========================
        # S2 — Unknown Event Type
        # ==========================
        for event in events:
            event_type = event.get("event_type")

            if event_type not in self.ALLOWED_EVENT_TYPES:
                fatal_errors.append(
                    ValidationError(
                        code="UNKNOWN_EVENT_TYPE",
                        execution_id=event.get("execution_id"),
                        message=f"Unknown event type: {event.get('event_type')}"
                    )
                )

        # ==========================
        # Execution Graph Validation
        # ==========================

        executions: Dict[str, Dict[str, Any]] = {}

        for event in events:
            execution_id = event.get("execution_id")

            if execution_id is None:
                continue

            if execution_id not in executions:
                executions[execution_id] = {
                    "started": False,
                    "finalized": False,
                    "steps": {},
                    "finalize_count": 0,
                }

            entry = executions[execution_id]

            # INTENT must start execution
            if event.get("event_type") == "INTENT_RECEIVED":
                entry["started"] = True

            # Step tracking
            if event.get("event_type") == "STEP_SENT":
                step_id = event.get("step_id")

                if step_id in entry["steps"]:
                    fatal_errors.append(
                        ValidationError(
                            "OVERLAPPING_STEPS",
                            execution_id,
                            f"Duplicate STEP_SENT for step {step_id}",
                        )
                    )

                entry["steps"][step_id] = {
                    "terminal": False
                }

            if event.get("event_type") in self.TERMINAL_STEP_EVENTS:
                step_id = event.get("step_id")

                if step_id not in entry["steps"]:
                    fatal_errors.append(
                        ValidationError(
                            "ORPHAN_TERMINAL_STEP",
                            execution_id,
                            f"Terminal event without STEP_SENT for step {step_id}",
                        )
                    )
                else:
                    if entry["steps"][step_id]["terminal"]:
                        fatal_errors.append(
                            ValidationError(
                                "DOUBLE_STEP_FINALIZATION",
                                execution_id,
                                f"Multiple terminal events for step {step_id}",
                            )
                        )
                    entry["steps"][step_id]["terminal"] = True

            if event.get("event_type") in self.FINALIZATION_EVENTS:
                entry["finalize_count"] += 1

                if entry["finalize_count"] > 1:
                    fatal_errors.append(
                        ValidationError(
                            "DOUBLE_EXECUTION_FINALIZATION",
                            execution_id,
                            "Execution finalized multiple times",
                        )
                    )

                entry["finalized"] = True

        # ==========================
        # Position Model Integrity
        # ==========================
        # Reducer state cross-check
        # ==========================

        if hasattr(reducer_state, "execution_state") and \
           reducer_state.execution_state == "READY" and \
           getattr(reducer_state, "active_execution_id", None) is not None:

            fatal_errors.append(
                ValidationError(
                    "INCONSISTENT_FINAL_STATE",
                    reducer_state.active_execution_id,
                    "READY state but active_execution_id not None",
                )
            )

        # ==========================
        # Circuit / Freeze Integrity
        # ==========================

        freeze_events = [
            e for e in events
            if e.get("event_type") == "SYSTEM_FROZEN"
        ]

        if reducer_state.circuit_consecutive_failures >= self.CIRCUIT_THRESHOLD:
            if not freeze_events:
                fatal_errors.append(
                    ValidationError(
                        "MISSING_FREEZE_EVENT",
                        None,
                        "Circuit threshold reached but SYSTEM_FROZEN missing",
                    )
                )

        for e in freeze_events:
            if reducer_state.circuit_consecutive_failures < self.CIRCUIT_THRESHOLD:
                fatal_errors.append(
                    ValidationError(
                        "INVALID_FREEZE_TRIGGER",
                        e.get("execution_id"),
                        "Freeze triggered below threshold",
                    )
                )

        # ==========================
        # Freeze consistency (production safe)
        # ==========================

        if hasattr(reducer_state, "freeze_flag"):

            if reducer_state.freeze_flag:

                freeze_events = [
                    e for e in events
                    if e.get("event_type") == "SYSTEM_FROZEN"
                ]

                if not freeze_events:
                    fatal_errors.append(
                        ValidationError(
                            "FREEZE_STATE_CORRUPTED",
                            None,
                            "freeze_flag true but no SYSTEM_FROZEN event",
                        )
                    )

        # ==========================
        # Final Result
        # ==========================

        return ValidationResult(
            valid=len(fatal_errors) == 0,
            fatal_errors=fatal_errors,
            warnings=warnings,
        )
