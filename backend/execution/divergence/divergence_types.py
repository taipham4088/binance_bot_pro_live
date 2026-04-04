from enum import Enum


class DivergenceType(str, Enum):
    NONE = "none"
    DECISION = "decision"
    STATE = "state"
    ORDER = "order"
