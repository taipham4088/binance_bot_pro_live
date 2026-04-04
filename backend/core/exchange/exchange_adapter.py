from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict


# =========================
# Exchange Models (Generic)
# =========================

@dataclass
class ExchangeOrder:
    order_id: str
    symbol: str
    side: str           # buy | sell
    qty: float
    price: Optional[float]
    status: str         # NEW | FILLED | CANCELED | REJECTED
    filled_qty: float = 0.0


@dataclass
class ExchangePosition:
    symbol: str
    size: float
    avg_price: float


# =========================
# Exchange Adapter Interface
# =========================

class ExchangeAdapter(ABC):
    """
    STEP 13.2 – ExchangeAdapter Interface

    Contract:
    - ExecutionEngine talks ONLY to this interface
    - No Control Plane access
    - No Strategy access
    """

    @abstractmethod
    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
    ) -> ExchangeOrder:
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> None:
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[ExchangePosition]:
        pass

    @abstractmethod
    def close_position(self, symbol: str) -> None:
        pass

    @abstractmethod
    def snapshot(self) -> Dict:
        pass
