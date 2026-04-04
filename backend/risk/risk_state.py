from dataclasses import dataclass, field
from typing import Dict
import time


@dataclass
class RiskState:
    """
    Runtime state for Risk Engine.

    This state is independent from ExecutionState and only tracks
    risk-related metrics such as trade counts, daily PnL and kill switch.
    """

    # -----------------------------
    # Risk control flags
    # -----------------------------

    kill_switch: bool = False

    # -----------------------------
    # PnL tracking
    # -----------------------------

    starting_equity: float = 10000.0
    equity: float = 10000.0
    daily_pnl: float = 0.0

    # -----------------------------
    # Trade statistics
    # -----------------------------

    trade_count_total: int = 0
    trade_count_today: int = 0
    trade_count_hour: int = 0

    last_trade_timestamp: int = 0

    # -----------------------------
    # Hour tracking
    # -----------------------------

    current_hour: int = field(default_factory=lambda: int(time.time() // 3600))

    # -----------------------------
    # Day tracking
    # -----------------------------

    current_day: int = field(default_factory=lambda: int(time.time() // 86400))

    # -----------------------------
    # Position exposure
    # -----------------------------

    current_position_size: float = 0.0

    # -----------------------------
    # Metadata
    # -----------------------------

    metadata: Dict = field(default_factory=dict)

    # =====================================================
    # PnL update
    # =====================================================

    def update_equity(self, equity: float):
        """
        Update current equity and calculate daily pnl.
        """
        self.equity = equity
        self.daily_pnl = equity - self.starting_equity

    # =====================================================
    # Trade event
    # =====================================================

    def register_trade(self, timestamp: int | None = None):
        """
        Register a trade event for frequency guards.
        """

        if timestamp is None:
            timestamp = int(time.time())

        # roll windows BEFORE counting
        self._roll_time_windows(timestamp)

        self.trade_count_total += 1
        self.trade_count_today += 1
        self.trade_count_hour += 1

        self.last_trade_timestamp = timestamp

    # =====================================================
    # Position exposure
    # =====================================================

    def update_position(self, size: float):
        """
        Track current position size for exposure guards.
        """
        self.current_position_size = abs(size)

    # =====================================================
    # Time window management
    # =====================================================

    def _roll_time_windows(self, timestamp: int):

        hour = timestamp // 3600
        day = timestamp // 86400

        # reset hourly counter
        if hour != self.current_hour:
            self.current_hour = hour
            self.trade_count_hour = 0

        # reset daily counter
        if day != self.current_day:
            self.current_day = day
            self.trade_count_today = 0
            self.daily_pnl = 0

    # =====================================================
    # Kill switch control
    # =====================================================

    def activate_kill_switch(self):
        """
        Permanently disable trading until manual reset.
        """
        self.kill_switch = True

    def reset_kill_switch(self):
        """
        Manual reset of kill switch.
        """
        self.kill_switch = False

    # =====================================================
    # Snapshot (for dashboard / logs)
    # =====================================================

    def snapshot(self):

        return {
            "equity": self.equity,
            "daily_pnl": self.daily_pnl,
            "trade_count_total": self.trade_count_total,
            "trade_count_today": self.trade_count_today,
            "trade_count_hour": self.trade_count_hour,
            "current_position_size": self.current_position_size,
            "kill_switch": self.kill_switch,
        }