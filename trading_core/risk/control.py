from trading_core.risk.commands import RiskCommand, RiskCommandType
from trading_core.risk.active_limits import ActiveRiskLimits
from trading_core.risk.supervisor import RiskSupervisor
from trading_core.risk.events import RiskEventType
from trading_core.risk.reason import RiskReason


class RiskControlManager:
    """
    STEP 7 – Phase 7.4

    Handles dashboard risk commands.
    """

    def __init__(self,
                 supervisor: RiskSupervisor,
                 active_limits: ActiveRiskLimits):
        self._sup = supervisor
        self._active = active_limits

    def handle(self, cmd: RiskCommand):

        if cmd.type == RiskCommandType.UPDATE_LIMITS:
            self._update_limits(cmd)

        elif cmd.type == RiskCommandType.FREEZE:
            self._sup.manual_freeze(RiskReason.MANUAL_FREEZE)

        elif cmd.type == RiskCommandType.UNFREEZE:
            self._manual_unfreeze(cmd)

        elif cmd.type == RiskCommandType.SAFE_MODE:
            self._toggle_safe_mode(cmd)

    # -------- internals --------

    def _update_limits(self, cmd: RiskCommand):
        self._active.update(
            daily_stop_pct=cmd.daily_stop_pct,
            daily_dd_block_pct=cmd.daily_dd_block_pct,
            max_position_size=cmd.max_position_size,
            max_notional=cmd.max_notional,
            max_trades_per_day=cmd.max_trades_per_day,
            allowed_symbols=cmd.allowed_symbols
        )

        self._sup._emit(RiskEventType.LIMIT_UPDATED)

    def _manual_unfreeze(self, cmd: RiskCommand):
        state = self._sup._get_state_ref()

        if state.dd_block_triggered:
            # DD block requires explicit admin decision.
            return

        self._sup.manual_unfreeze()

    def _toggle_safe_mode(self, cmd: RiskCommand):
        self._active.safe_mode = bool(cmd.safe_mode)
