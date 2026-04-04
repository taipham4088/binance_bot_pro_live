from dataclasses import dataclass


@dataclass
class FillResult:
    filled_quantity: float
    status: str
    raw: dict
