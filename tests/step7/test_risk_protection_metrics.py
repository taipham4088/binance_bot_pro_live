from trading_core.risk.protection import RiskProtectionEngine
from trading_core.risk.limits import RiskLimits


def test_daily_metrics_update(risk_supervisor):

    limits = RiskLimits(daily_stop_pct=0.02)
    engine = RiskProtectionEngine(risk_supervisor, limits)

    engine.on_equity_update(
        equity=950,
        balance=950,
        realized_pnl=-50,
        unrealized_pnl=0
    )

    s = risk_supervisor.snapshot()
    assert s.daily_pnl == -50
    assert s.daily_drawdown == 50
