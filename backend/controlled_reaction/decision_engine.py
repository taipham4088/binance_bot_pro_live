from typing import List, Optional

from .reaction_contract import (
    SeverityLevel,
    ReactionType,
    InvariantViolation,
    ReactionDecision,
)


class Phase45DecisionEngine:
    """
    Phase 4.5 – Controlled Reaction Engine
    Pure decision logic, side-effect free.
    """

    @staticmethod
    def decide(
        *,
        reconciliation_id: Optional[str],
        severity: SeverityLevel,
        invariant_violations: Optional[List[InvariantViolation]] = None,
    ) -> ReactionDecision:

        invariant_violations = invariant_violations or []

        # ===== DEFAULT SAFE PATH =====
        if severity == SeverityLevel.INFO:
            return ReactionDecision(
                reaction=ReactionType.NONE,
                severity=SeverityLevel.INFO,
                reason="INFO severity – no reaction",
                invariants=invariant_violations,
                reconciliation_id=reconciliation_id,
            )

        # ===== WARN =====
        if severity == SeverityLevel.WARN:
            return ReactionDecision(
                reaction=ReactionType.NOTIFY,
                severity=SeverityLevel.WARN,
                reason="WARN severity – notify human",
                invariants=invariant_violations,
                notify_human=True,
                reconciliation_id=reconciliation_id,
            )

        # ===== ERROR =====
        if severity == SeverityLevel.ERROR:
            return ReactionDecision(
                reaction=ReactionType.FREEZE,
                severity=SeverityLevel.ERROR,
                reason="ERROR severity – freeze execution",
                invariants=invariant_violations,
                freeze_execution=True,
                notify_human=True,
                reconciliation_id=reconciliation_id,
            )

        # ===== CRITICAL =====
        if severity == SeverityLevel.CRITICAL:
            return ReactionDecision(
                reaction=ReactionType.ESCALATE,
                severity=SeverityLevel.CRITICAL,
                reason="CRITICAL severity – freeze and escalate",
                invariants=invariant_violations,
                freeze_execution=True,
                notify_human=True,
                escalate_human=True,
                reconciliation_id=reconciliation_id,
            )

        # ===== FAIL SAFE =====
        return ReactionDecision(
            reaction=ReactionType.NONE,
            severity=SeverityLevel.INFO,
            reason="Unknown severity – fail safe",
            invariants=invariant_violations,
            reconciliation_id=reconciliation_id,
        )
