from dataclasses import dataclass
from typing import List, Dict, Optional


# =========================
# Strategy Intent Models
# =========================

@dataclass
class TradeIntent:
    """
    Intent emitted by a strategy.
    Strategy MUST NOT execute directly.
    """
    strategy_id: str
    symbol: str
    direction: str        # long | short
    size: float           # normalized size (0.0 ~ 1.0)
    priority: int         # higher = stronger


@dataclass
class ResolvedIntent:
    """
    Final resolved intent sent to ExecutionEngine.
    """
    symbol: str
    side: str             # buy | sell
    qty: float
    source_strategies: List[str]


# =========================
# Strategy Orchestrator
# =========================

class StrategyOrchestrator:
    """
    STEP 11 / Module 4

    Responsibilities:
    - Accept TradeIntent from multiple strategies
    - Resolve direction by priority
    - Resolve size by weighted aggregation
    - Emit ONE ResolvedIntent per symbol
    - NO execution authority
    """

    def __init__(self, max_position_size: float):
        self.max_position_size = max_position_size

    # -------------------------
    # Public API
    # -------------------------

    def resolve(self, intents: List[TradeIntent]) -> List[ResolvedIntent]:
        """
        Resolve multiple TradeIntent into executable intents.
        """

        if not intents:
            return []

        grouped: Dict[str, List[TradeIntent]] = {}
        for intent in intents:
            grouped.setdefault(intent.symbol, []).append(intent)

        resolved: List[ResolvedIntent] = []

        for symbol, symbol_intents in grouped.items():
            resolved_intent = self._resolve_symbol(symbol, symbol_intents)
            if resolved_intent:
                resolved.append(resolved_intent)

        return resolved

    # -------------------------
    # Symbol Resolution
    # -------------------------

    def _resolve_symbol(
        self,
        symbol: str,
        intents: List[TradeIntent]
    ) -> Optional[ResolvedIntent]:
        """
        Resolve intents for ONE symbol.
        """

        # 1. Resolve direction by highest priority
        intents_sorted = sorted(
            intents,
            key=lambda x: x.priority,
            reverse=True
        )

        top = intents_sorted[0]
        direction = top.direction

        # 2. Filter intents matching direction
        aligned = [
            i for i in intents_sorted
            if i.direction == direction
        ]

        if not aligned:
            return None

        # 3. Weighted size aggregation
        total_weight = sum(i.priority for i in aligned)
        if total_weight <= 0:
            return None

        weighted_size = sum(
            (i.size * i.priority) for i in aligned
        ) / total_weight

        # Clamp
        final_qty = max(
            0.0,
            min(weighted_size * self.max_position_size, self.max_position_size)
        )

        if final_qty <= 0:
            return None

        side = "buy" if direction == "long" else "sell"

        return ResolvedIntent(
            symbol=symbol,
            side=side,
            qty=final_qty,
            source_strategies=[i.strategy_id for i in aligned],
        )
