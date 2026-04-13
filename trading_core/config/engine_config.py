from dataclasses import dataclass

@dataclass
class EngineConfig:
    initial_balance: float
    risk_per_trade: float
    symbol: str = "BTCUSDT"

    # exchange selection (multi-exchange ready)
    exchange: str = "binance"

    # execution mode
    mode: str = "paper"  # paper | shadow | live

    # core
    core_mode: str = "locked"     # locked | research
    trade_mode: str = "dual"      # long | short | dual

    # locked core params
    rr_locked: float = 2.5

    # research params
    rr: float = 2.5

    # daily rules
    daily_stop_losses: int = 2
    daily_dd_limit: float = 0.03

    # time
    timezone_offset_hours: int = 7

    # strategy registry key (range_trend, range_trend_1m, …) — DualEngine + market TF profile
    engine: str = "range_trend"

    def __post_init__(self):
        print("[ENGINE CONFIG INIT]")
        print(self.trade_mode)
