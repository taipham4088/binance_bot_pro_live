from dataclasses import dataclass
from typing import Optional
import time

# Daily equity drawdown limit as a fraction (e.g. 0.06 = 6%); aligned with session risk_config.
_DEFAULT_DAILY_DD_LIMIT_FRAC = 0.06


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
    - Daily equity drawdown from first trade of UTC day (exchange equity), not journal / peak curve
    - Kill-switch: manual / legacy only (peak-trough no longer arms kill_switch)
    """

    DAILY_STOP_LOSSES = 2
    MAX_DRAWDOWN_PCT = -6.0   # legacy display constant; daily limit uses daily_dd_limit_frac
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

        # --- Daily equity drawdown (first OPENED/CLOSED of UTC day, external equity) ---
        self.daily_date: Optional[str] = None
        self.daily_started: bool = False
        self.daily_start_equity: Optional[float] = None
        self.daily_dd_blocked: bool = False
        self.daily_drawdown_pct: float = 0.0
        self.daily_dd_limit_frac: float = _DEFAULT_DAILY_DD_LIMIT_FRAC

    # -------------------------
    # Public Guards
    # -------------------------

    def can_open_new_position(self, qty: float) -> bool:
        """
        Entry guard.
        """

        if self.drawdown.kill_switch_triggered:
            return False

        if self.daily_dd_blocked:
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
    # Daily equity drawdown (exchange / session equity)
    # -------------------------

    def set_daily_dd_limit_frac(self, limit_frac: float) -> None:
        if limit_frac is not None and float(limit_frac) > 0:
            self.daily_dd_limit_frac = float(limit_frac)

    def _roll_daily_equity_utc(self) -> None:
        today = self._today_key()
        if self.daily_date != today:
            self.daily_date = today
            self.daily_started = False
            self.daily_start_equity = None
            self.daily_dd_blocked = False
            self.daily_drawdown_pct = 0.0

    def tick_daily_drawdown(
        self,
        current_equity: float,
        trade_decision: Optional[str],
        limit_frac: Optional[float] = None,
    ) -> None:
        """
        trade_decision: 'OPENED' | 'CLOSED' from execution events, or None to refresh only.
        current_equity: wallet equity in quote (caller uses session.get_dynamic_equity()).
        """
        if limit_frac is not None and float(limit_frac) > 0:
            self.daily_dd_limit_frac = float(limit_frac)

        self._roll_daily_equity_utc()

        if trade_decision in ("OPENED", "CLOSED") and not self.daily_started:
            self.daily_start_equity = float(current_equity)
            self.daily_started = True

        self._recompute_daily_dd_pct_block(float(current_equity))

    def _recompute_daily_dd_pct_block(self, current_equity: float) -> None:
        if not self.daily_started:
            self.daily_dd_blocked = False
            self.daily_drawdown_pct = 0.0
            return

        start = self.daily_start_equity
        if start is None or start <= 0:
            self.daily_dd_blocked = False
            self.daily_drawdown_pct = 0.0
            return

        dd_frac = (current_equity - start) / start
        self.daily_drawdown_pct = dd_frac * 100.0
        lim = float(self.daily_dd_limit_frac)
        self.daily_dd_blocked = dd_frac <= -lim

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
        Peak-to-trough from internal equity model (trade PnL % chain).
        Does NOT arm kill_switch — that falsely blocks live when journal/history is deep red.
        """
        peak = self.drawdown.peak_equity
        current = self.drawdown.current_equity

        if peak > 0:
            dd_pct = ((current - peak) / peak) * 100.0
            self.drawdown.max_drawdown_pct = dd_pct

    # -------------------------
    # Daily Rollover
    # -------------------------

    def _roll_daily_if_needed(self) -> None:
        today = self._today_key()
        if today != self.daily.date_key:
            self.daily = DailyRiskState(date_key=today)
            self._roll_daily_equity_utc()

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
            },
            "daily_equity": {
                "daily_date": self.daily_date,
                "daily_started": self.daily_started,
                "daily_start_equity": self.daily_start_equity,
                "daily_drawdown_pct": self.daily_drawdown_pct,
                "daily_limit_frac": self.daily_dd_limit_frac,
                "daily_limit_pct": self.daily_dd_limit_frac * 100.0,
                "daily_dd_blocked": self.daily_dd_blocked,
            },
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
