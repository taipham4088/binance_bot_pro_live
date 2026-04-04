from trading_core.risk.state import RiskState
from trading_core.risk.limits import RiskLimits
from trading_core.risk.reason import RiskReason
from trading_core.risk.supervisor import RiskSupervisor


class RiskProtectionEngine:
    """
    STEP 7 – Phase 7.3
    Auto daily stop & daily drawdown block detector.
    """

    def __init__(self, supervisor: RiskSupervisor, limits: RiskLimits):
        self._sup = supervisor
        self._limits = limits

    def on_equity_update(self,
                          equity: float,
                          balance: float,
                          realized_pnl: float,
                          unrealized_pnl: float):

        # 1. update raw truth
        self._sup.update_equity(
            equity=equity,
            balance=balance,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl
        )

        # ⚠️ lấy reference thật, không phải snapshot
        state = self._sup._get_state_ref()

        # 2. recompute metrics ON REAL STATE
        self._recompute_metrics(state)

        # 3. enforce protections
        self._check_daily_stop(state)
        self._check_dd_block(state)

    # ---------- internal ----------

    def _recompute_metrics(self, state: RiskState):

        state.daily_pnl = state.balance - state.day_start_balance

        if state.balance < state.day_start_balance:
            state.daily_drawdown = state.day_start_balance - state.balance
        else:
            state.daily_drawdown = 0.0

        if state.equity < state.peak_equity:
            state.session_drawdown = state.peak_equity - state.equity
            state.max_drawdown = max(state.max_drawdown, state.session_drawdown)
        else:
            state.session_drawdown = 0.0

    def _check_daily_stop(self, state: RiskState):

        if state.daily_stop_triggered:
            return

        if self._limits.daily_stop_pct is None:
            return

        max_loss = state.day_start_balance * self._limits.daily_stop_pct

        if state.daily_drawdown >= max_loss:
            self._sup.trigger_daily_stop()

    def _check_dd_block(self, state: RiskState):

        if state.dd_block_triggered:
            return

        if self._limits.daily_dd_block_pct is None:
            return

        max_dd = state.peak_equity * self._limits.daily_dd_block_pct

        if state.session_drawdown >= max_dd:
            self._sup.trigger_dd_block()
            self._sup.manual_freeze(RiskReason.DAILY_DD_BLOCK)
