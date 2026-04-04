from dataclasses import dataclass
from typing import Dict, Optional
import time


# =========================
# Reversal Warning Models
# =========================

@dataclass
class ReversalSignal:
    """
    Signal generated from backtested engine-long / engine-short.
    """
    symbol: str
    direction: str        # long | short
    confidence: float     # 0.0 ~ 1.0
    source: str           # engine_long | engine_short
    timestamp: float


@dataclass
class ReversalWarningState:
    """
    Current warning state per symbol.
    """
    symbol: str
    active: bool
    direction: Optional[str]
    confidence: float
    source: Optional[str]
    last_updated: float


# =========================
# Reversal Warning Engine
# =========================

class ReversalWarningEngine:
    """
    STEP 11 / Module 5

    Responsibilities:
    - Receive reversal signals from backtested engines
    - Maintain observer-only warning state
    - Expose snapshot for dashboard / observer
    - NO execution authority
    """

    def __init__(self, confidence_threshold: float = 0.7):
        self.confidence_threshold = confidence_threshold
        self._states: Dict[str, ReversalWarningState] = {}

    # -------------------------
    # Signal Ingest
    # -------------------------

    def ingest(self, signal: ReversalSignal) -> None:
        """
        Ingest reversal signal.
        Does NOT trigger any execution.
        """

        if signal.confidence < self.confidence_threshold:
            # Below threshold → clear warning
            self._states[signal.symbol] = ReversalWarningState(
                symbol=signal.symbol,
                active=False,
                direction=None,
                confidence=signal.confidence,
                source=signal.source,
                last_updated=signal.timestamp,
            )
            return

        # Activate warning
        self._states[signal.symbol] = ReversalWarningState(
            symbol=signal.symbol,
            active=True,
            direction=signal.direction,
            confidence=signal.confidence,
            source=signal.source,
            last_updated=signal.timestamp,
        )

    # -------------------------
    # Observer API
    # -------------------------

    def get_warning(self, symbol: str) -> Optional[ReversalWarningState]:
        return self._states.get(symbol)

    def snapshot(self) -> Dict[str, dict]:
        """
        Read-only snapshot for dashboard / observer plane.
        """
        return {
            symbol: {
                "active": state.active,
                "direction": state.direction,
                "confidence": state.confidence,
                "source": state.source,
                "last_updated": state.last_updated,
            }
            for symbol, state in self._states.items()
        }
