from backend.core.exchange.exchange_adapter import ExchangeAdapter
from typing import Dict, Optional, List
from dataclasses import dataclass
import time

# Local imports (đã làm ở Module 1 & 2)
from backend.core.execution.execution_slot_manager import (
    ExecutionSlotManager,
    ExecutionSlotKey,
)
from backend.core.risk.risk_engine import RiskEngine, TradeResult


# =========================
# Execution Models
# =========================

@dataclass
class OrderIntent:
    symbol: str
    side: str            # buy | sell
    qty: float
    intent_id: str
    reduce_only: bool = False     
    reverse_explicit: bool = False

@dataclass
class PositionState:
    symbol: str
    size: float = 0.0
    entry_price: float = 0.0


# =========================
# Execution Engine
# =========================

class ExecutionEngine:
    """
    STEP 11 / Module 3

    Responsibilities:
    - Own execution lifecycle of ONE session
    - Enforce slot ownership
    - Enforce risk guards BEFORE entry
    - Maintain symbol-level position state
    - NO exchange adapter here (hook later)
    """

    def __init__(
        self,
        session_id: str,
        mode: str,                     # live | paper | backtest
        slot_key: ExecutionSlotKey,
        slot_manager: ExecutionSlotManager,
        risk_engine: RiskEngine,
        exchange_adapter: ExchangeAdapter,
        taker_fee_pct: float = 0.04,      # 0.04% ví dụ Binance
        slippage_pct: float = 0.01,       # 0.01% mặc định
    ):
        self.session_id = session_id
        self.mode = mode
        self.slot_key = slot_key
        self.slot_manager = slot_manager
        self.risk = risk_engine
        self.taker_fee_pct = taker_fee_pct
        self.slippage_pct = slippage_pct


        self.running: bool = False
        self.positions: Dict[str, PositionState] = {}
        self.exchange = exchange_adapter

    # -------------------------
    # Lifecycle
    # -------------------------

    def start(self) -> bool:
        """
        Acquire execution slot and start engine.
        """
        acquired = self.slot_manager.acquire_slot(
            key=self.slot_key,
            session_id=self.session_id,
            mode=self.mode,
        )

        if not acquired:
            return False

        self.running = True
        return True

    def stop(self) -> None:
        """
        Stop engine and release slot.
        """
        self.running = False
        self.slot_manager.release_slot(
            key=self.slot_key,
            session_id=self.session_id,
        )

    # -------------------------
    # Entry Guard
    # -------------------------

    def can_execute(self) -> bool:
        """
        Unified guard before any execution.
        """
        if not self.running:
            return False

        if self.mode == "backtest":
            return False  # observer-only

        if not self.risk.can_open_new_position():
            return False

        return True

    # -------------------------
    # Intent Handling
    # -------------------------
    def _pos_side(self, size: float) -> str:
        return "long" if size > 0 else "short"


    def handle_order_intent(self, intent: OrderIntent) -> bool:
        """
        Accepts resolved intent from StrategyOrchestrator.
        Does NOT talk to exchange.
        """

        if not self.can_execute():
            return False

        pos = self.positions.get(intent.symbol)

        # 4️⃣ Reverse explicit = 2 pha (đóng → FLAT → mở)
        if pos and intent.reverse_explicit:
            incoming_delta = intent.qty if intent.side == "buy" else -intent.qty

            # Chỉ xử lý khi NGƯỢC chiều position hiện tại
            if pos.size * incoming_delta < 0:
                # Pha 1: đóng hết (reduce-only)
                close_side = "sell" if pos.size > 0 else "buy"
                close_intent = OrderIntent(
                    symbol=intent.symbol,
                    side=close_side,
                    qty=abs(pos.size),
                    intent_id=f"{intent.intent_id}:close",
                    reduce_only=True,
                ) 

                if not self._update_position(close_intent):
                    return False

                # Chưa FLAT thì dừng (tuyệt đối không mở chiều mới)
                if intent.symbol in self.positions:
                    return False

                # Pha 2: mở chiều mới
                return self._open_position(intent)

        # Open new position (chỉ khi đang FLAT)
        if pos is None or pos.size == 0:
            return self._open_position(intent)

        # Same direction add / reduce logic (reduce-only guard nằm trong _update_position)
        return self._update_position(intent)

    # -------------------------
    # Position Logic
    # -------------------------

    def _open_position(self, intent: OrderIntent) -> bool:
        """
        Open new position via ExchangeAdapter.
        """
        order = self.exchange.place_market_order(
            symbol=intent.symbol,
            side=intent.side,
            qty=intent.qty,
        )

        if order.status != "FILLED":
            return False

        raw_price = order.price or 0.0
        if raw_price <= 0:
            return False

        # Slippage bất lợi
        slip = raw_price * (self.slippage_pct / 100.0)
        entry_price = (
            raw_price + slip if intent.side == "buy"
            else raw_price - slip          
        )

        size = intent.qty if intent.side == "buy" else -intent.qty

        self.positions[intent.symbol] = PositionState(
            symbol=intent.symbol,
            size=size,
            entry_price=entry_price,
        )
        return True

    def _update_position(self, intent: OrderIntent) -> bool:
        pos = self.positions[intent.symbol]
        prev_size = pos.size

        delta = intent.qty if intent.side == "buy" else -intent.qty

        # Reduce-only: không cho tăng size
        if intent.reduce_only:
            if prev_size * delta > 0:
                return False

        order = self.exchange.place_market_order(
            symbol=intent.symbol,
            side=intent.side,
            qty=intent.qty,
        )

        if order.status != "FILLED":
            return False

        pos.size += delta

        # Fully closed
        if pos.size == 0:
            raw_exit = order.price or 0.0

            slip = raw_exit * (self.slippage_pct / 100.0)
            exit_price = (
                raw_exit - slip if intent.side == "sell"
                else raw_exit + slip
            )

            pnl_pct = self._calculate_pnl_pct(
                entry_price=pos.entry_price,
                exit_price=exit_price,
                side=self._pos_side(prev_size),
            )

            self._on_position_closed(
                symbol=intent.symbol,
                pnl_pct=pnl_pct,
            )

        return True

    def _calculate_pnl_pct(
        self,
        entry_price: float,
        exit_price: float,
        side: str,   # long | short
    ) -> float:
        """
        Calculate net PnL percentage including fees.
        """
        if entry_price <= 0:
            return 0.0

        gross = (
            (exit_price - entry_price) / entry_price
            if side == "long"
            else (entry_price - exit_price) / entry_price
        )

        # Fee: entry + exit
        fee_total = 2 * (self.taker_fee_pct / 100.0)

        net = gross - fee_total
        return net * 100.0


    # -------------------------
    # Close & Risk Update
    # -------------------------

    def _on_position_closed(self, symbol: str, pnl_pct: float) -> None:
        """
        Called AFTER a position is fully closed.
        """
        result = TradeResult(
            pnl_pct=pnl_pct,
            closed_at=time.time(),
        )
        self.risk.register_trade_close(result)
        del self.positions[symbol]

    # -------------------------
    # Observer Snapshot
    # -------------------------

    def snapshot(self) -> dict:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "running": self.running,
            "positions": {
                s: {
                    "size": p.size,
                    "entry_price": p.entry_price,
                }
                for s, p in self.positions.items()
            },
            "risk": self.risk.snapshot(),
        }
