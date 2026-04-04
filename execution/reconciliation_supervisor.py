# execution/reconciliation_supervisor.py

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ReconciliationStatus(str, Enum):
    SYNCED = "SYNCED"
    SOFT_DESYNC = "SOFT_DESYNC"
    HARD_DESYNC = "HARD_DESYNC"


@dataclass
class PositionSnapshot:
    side: str  # "long" | "short" | "flat"
    size: float


@dataclass
class ReconciliationResult:
    status: ReconciliationStatus
    reason: str


class ReconciliationSupervisor:
    """
    Production-grade reconciliation detector.

    This component:
        - Compares timeline position vs exchange position
        - Classifies desync level
        - Does NOT mutate state
        - Does NOT execute trades
    """

    def __init__(self, soft_tolerance: float = 0.02):
        """
        soft_tolerance:
            Percentage tolerance for partial fill mismatch.
            Example:
                timeline = 1.0
                exchange = 0.99
                diff = 1%
                → SOFT_DESYNC
        """
        self.soft_tolerance = soft_tolerance

    # =========================================================
    # PUBLIC API
    # =========================================================

    def reconcile(
        self,
        timeline_position: PositionSnapshot,
        exchange_position: PositionSnapshot,
    ) -> ReconciliationResult:

        # 1️⃣ Both flat
        if timeline_position.side == "flat" and exchange_position.side == "flat":
            return ReconciliationResult(
                status=ReconciliationStatus.SYNCED,
                reason="both_flat",
            )

        # 2️⃣ Same side
        if timeline_position.side == exchange_position.side:
            return self._compare_same_side(
                timeline_position,
                exchange_position,
            )

        # 3️⃣ Different side or unexpected
        return ReconciliationResult(
            status=ReconciliationStatus.HARD_DESYNC,
            reason="side_mismatch",
        )

    # =========================================================
    # INTERNAL
    # =========================================================

    def _compare_same_side(
        self,
        timeline_position: PositionSnapshot,
        exchange_position: PositionSnapshot,
    ) -> ReconciliationResult:

        # If one flat and other not → HARD
        if timeline_position.side == "flat" and exchange_position.side != "flat":
            return ReconciliationResult(
                status=ReconciliationStatus.HARD_DESYNC,
                reason="unexpected_live_position",
            )

        if timeline_position.side != "flat" and exchange_position.side == "flat":
            return ReconciliationResult(
                status=ReconciliationStatus.HARD_DESYNC,
                reason="missing_live_position",
            )

        timeline_size = abs(timeline_position.size)
        exchange_size = abs(exchange_position.size)

        if timeline_size == 0 and exchange_size == 0:
            return ReconciliationResult(
                status=ReconciliationStatus.SYNCED,
                reason="zero_size_match",
            )

        if timeline_size == 0 or exchange_size == 0:
            return ReconciliationResult(
                status=ReconciliationStatus.HARD_DESYNC,
                reason="zero_size_mismatch",
            )

        diff = abs(timeline_size - exchange_size)

        # Exact match → SYNCED
        if diff == 0:
            return ReconciliationResult(
                status=ReconciliationStatus.SYNCED,
                reason="exact_match",
            )

        ratio = diff / timeline_size

        # Within tolerance → SOFT
        if ratio <= self.soft_tolerance:
            return ReconciliationResult(
                status=ReconciliationStatus.SOFT_DESYNC,
                reason="size_within_tolerance",
            )

        # Otherwise → HARD
        return ReconciliationResult(
            status=ReconciliationStatus.HARD_DESYNC,
            reason="size_out_of_tolerance",
        )

        