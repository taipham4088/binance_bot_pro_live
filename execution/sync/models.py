from dataclasses import dataclass, field
from typing import Dict
import time


@dataclass
class AccountState:
    balances: Dict[str, float] = field(default_factory=dict)
    available: Dict[str, float] = field(default_factory=dict)
    last_update: float = field(default_factory=time.time)


@dataclass
class PositionState:
    symbol: str
    side: str
    size: float
    entry_price: float
    unrealized_pnl: float
    leverage: float
    last_update: float


@dataclass
class OrderState:
    order_id: str
    client_id: str
    symbol: str
    side: str
    status: str
    price: float | None
    qty: float
    filled: float
    last_update: float
