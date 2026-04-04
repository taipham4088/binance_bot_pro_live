from dataclasses import dataclass
from .models import AccountState, PositionState, OrderState


@dataclass
class AccountUpdated:
    state: AccountState


@dataclass
class PositionUpdated:
    position: PositionState


@dataclass
class PositionClosed:
    symbol: str
    side: str


@dataclass
class OrderUpdated:
    order: OrderState
