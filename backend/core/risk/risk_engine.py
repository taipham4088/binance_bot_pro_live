from dataclasses import dataclass
from typing import Optional
import time


# =========================
# Risk State Models
# =========================

@dataclass
class TradeResult:
    pnl_pct: float          # % PnL của trade (+/-)
    closed_at: float


@dataclass
class DailyRiskState:
    date_key: str           # YYYY-MM-DD
    consecutive_losses: int = 0
    entry_blocked: bool = False


@dataclass
class DrawdownState:
    peak_equity: float
    current_equity: float
    max_drawdown_pct: float
    kill_switch_triggered: bool = False


# =========================
# Risk Engine
# =========================

class RiskEngine:
    """
    Enforces STEP 10 policies:
    - Daily Stop (2 consecutive losing trades)
    - Max Drawdown (-6%)
    - Kill-switch behavior (state only, no execution)
    """

    DAILY_STOP_LOSSES = 2
    MAX_DRAWDOWN_PCT = -6.0   # absolute %

    MAX_POSITION_SIZE = 1.0
    MAX_TRADES_PER_MIN = 10

    def __init__(self, initial_equity: float):
        self.initial_equity = initial_equity

        self.drawdown = DrawdownState(
            peak_equity=initial_equity,
            current_equity=initial_equity,
            max_drawdown_pct=0.0,
            kill_switch_triggered=False
        )

        today = self._today_key()
        self.daily = DailyRiskState(date_key=today)

        self.trade_timestamps = []

    # -------------------------
    # Public Guards
    # -------------------------

    def can_open_new_position(self, qty: float) -> bool:
        """
        Entry guard.
        """

        if self.drawdown.kill_switch_triggered:
            return False

        if self.daily.entry_blocked:
            return False

        if qty > self.MAX_POSITION_SIZE:
            return False

        if not self._check_frequency():
            return False

        return True

    def is_kill_switch_active(self) -> bool:
        return self.drawdown.kill_switch_triggered

    # -------------------------
    # Trade Update
    # -------------------------

    def register_trade_close(self, result: TradeResult) -> None:
        """
        Called when a position is fully closed.
        """

        self._roll_daily_if_needed()
        self._update_equity(result.pnl_pct)
        self._update_daily_stop(result.pnl_pct)
        self._update_drawdown()

    def register_trade_open(self):
        self.trade_timestamps.append(time.time())

    # -------------------------
    # Internal Logic
    # -------------------------

    def _update_equity(self, pnl_pct: float) -> None:
        """
        Update equity based on trade PnL percentage.
        """
        self.drawdown.current_equity *= (1 + pnl_pct / 100.0)

        if self.drawdown.current_equity > self.drawdown.peak_equity:
            self.drawdown.peak_equity = self.drawdown.current_equity

    def _update_daily_stop(self, pnl_pct: float) -> None:
        """
        Track consecutive losses for daily stop.
        """
        if pnl_pct < 0:
            self.daily.consecutive_losses += 1
        else:
            self.daily.consecutive_losses = 0

        if self.daily.consecutive_losses >= self.DAILY_STOP_LOSSES:
            self.daily.entry_blocked = True

    def _update_drawdown(self) -> None:
        """
        Check max drawdown and trigger kill-switch if exceeded.
        """
        peak = self.drawdown.peak_equity
        current = self.drawdown.current_equity

        dd_pct = ((current - peak) / peak) * 100.0
        self.drawdown.max_drawdown_pct = dd_pct

        if dd_pct <= self.MAX_DRAWDOWN_PCT:
            self.drawdown.kill_switch_triggered = True

    # -------------------------
    # Daily Rollover
    # -------------------------

    def _roll_daily_if_needed(self) -> None:
        today = self._today_key()
        if today != self.daily.date_key:
            self.daily = DailyRiskState(date_key=today)

    def _today_key(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    # -------------------------
    # Read-only State (Observer)
    # -------------------------

    def snapshot(self) -> dict:
        return {
            "daily": {
                "date": self.daily.date_key,
                "consecutive_losses": self.daily.consecutive_losses,
                "entry_blocked": self.daily.entry_blocked,
            },
            "drawdown": {
                "peak_equity": self.drawdown.peak_equity,
                "current_equity": self.drawdown.current_equity,
                "max_drawdown_pct": self.drawdown.max_drawdown_pct,
                "kill_switch": self.drawdown.kill_switch_triggered,
            }
            "frequency": {
                "trades_last_min": len(self.trade_timestamps),
                "limit": self.MAX_TRADES_PER_MIN
            }
        }

    def _check_frequency(self) -> bool:

        now = time.time()

        # remove trades older than 60s
        self.trade_timestamps = [
            t for t in self.trade_timestamps
            if now - t < 60
        ]

        if len(self.trade_timestamps) >= self.MAX_TRADES_PER_MIN:
            return False

        return True
