from backend.analytics.pnl_engine import PnLEngine

pnl = PnLEngine()

print("REALIZED PNL:", pnl.realized_pnl())

print("EQUITY:", pnl.equity())

print("EQUITY CURVE:", pnl.equity_curve())

print("MAX DRAWDOWN:", pnl.max_drawdown())

print("SUMMARY:", pnl.summary())