from trading_core.risk.protection import RiskProtectionEngine
from trading_core.risk.limits import RiskLimits
from trading_core.risk.reason import RiskReason


def test_dd_block_freeze(risk_supervisor):

    limits = RiskLimits(daily_dd_block_pct=0.05)  # 5%
    engine = RiskProtectionEngine(risk_supervisor, limits)

    # peak equity = 1000 → dd 60 = 6%
    engine.on_equity_update(
        equity=940,
        balance=940,
        realized_pnl=-60,
        unrealized_pnl=0
    )

    s = risk_supervisor.snapshot()
    assert s.dd_block_triggered is True
    assert s.frozen is True
    assert s.freeze_reason == RiskReason.DAILY_DD_BLOCK
