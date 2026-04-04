import copy
from datetime import date
from typing import List

from trading_core.risk.state import RiskState
from trading_core.risk.events import RiskEvent, RiskEventType
from trading_core.risk.reason import RiskReason


class RiskSupervisor:
    """
    Phase 7.1 role:
    - single holder of RiskState
    - update truth
    - manage daily rollover
    - set protection flags
    - freeze system
    - emit risk events

    (NO limit checking, NO verdicts, NO orchestrator control yet)
    """

    def __init__(self, initial_state: RiskState):
        self._state = initial_state
        self._events: List[RiskEvent] = []

    # -------- access --------

    def snapshot(self) -> RiskState:
        return copy.deepcopy(self._state)

    def events(self) -> List[RiskEvent]:
        return list(self._events)

    # -------- truth updates --------

    def update_equity(self, equity: float, balance: float,
                      realized_pnl: float, unrealized_pnl: float):

        self._state.equity = equity
        self._state.balance = balance
        self._state.realized_pnl = realized_pnl
        self._state.unrealized_pnl = unrealized_pnl

        if equity > self._state.peak_equity:
            self._state.peak_equity = equity

        self._emit(RiskEventType.STATE_UPDATE)

    def update_exposure(self, exposure_by_symbol: dict[str, float]):
        self._state.exposure_by_symbol = exposure_by_symbol
        self._emit(RiskEventType.STATE_UPDATE)

    def mark_trade(self, ts: float, is_reverse: bool = False):
        self._state.trades_today += 1
        if is_reverse:
            self._state.reverses_today += 1
        self._state.last_trade_ts = ts
        self._emit(RiskEventType.STATE_UPDATE)

    # -------- daily rollover --------

    def rollover_day(self, new_day: date):
        if new_day == self._state.trading_day:
            return

        self._state.trading_day = new_day
        self._state.day_start_balance = self._state.balance
        self._state.daily_pnl = 0.0
        self._state.daily_drawdown = 0.0

        self._state.trades_today = 0
        self._state.reverses_today = 0

        self._state.daily_stop_triggered = False
        self._state.dd_block_triggered = False

        self._emit(RiskEventType.DAILY_RESET)

    # -------- protection flags --------

    def trigger_daily_stop(self):
        if not self._state.daily_stop_triggered:
            self._state.mark_daily_stop()
            self._emit(RiskEventType.DAILY_STOP_TRIGGERED, RiskReason.DAILY_STOP)

    def trigger_dd_block(self):
        if not self._state.dd_block_triggered:
            self._state.mark_dd_block()
            self._emit(RiskEventType.DD_BLOCK_TRIGGERED, RiskReason.DAILY_DD_BLOCK)

    # -------- system power --------

    def manual_freeze(self, reason: RiskReason):
        if not self._state.frozen:
            self._state.freeze(reason)
            self._emit(RiskEventType.FREEZE, reason)

    def manual_unfreeze(self):
        if self._state.frozen:
            self._state.frozen = False
            self._state.freeze_reason = None
            self._emit(RiskEventType.UNFREEZE)

    # -------- event --------

    def _emit(self, event_type: RiskEventType,
              reason: RiskReason | None = None):
        self._events.append(
            RiskEvent.now(event_type, self.snapshot(), reason)
        )

    # ⚠️ internal use only (risk engines)
    def _get_state_ref(self) -> RiskState:
        return self._state
