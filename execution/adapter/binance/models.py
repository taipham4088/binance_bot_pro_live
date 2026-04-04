from dataclasses import dataclass
from typing import Optional
from enum import Enum
import time


class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class InternalOrder:
    order_id: str
    client_id: str
    symbol: str
    side: str
    position_side: str
    order_type: str
    price: Optional[float]
    qty: float
    filled: float
    status: OrderStatus
    update_ts: float


@dataclass
class InternalPosition:
    symbol: str
    side: str
    size: float
    entry_price: float
    unrealized_pnl: float
    leverage: float
    update_ts: float


@dataclass
class InternalBalance:
    asset: str
    wallet: float
    available: float
    update_ts: float
