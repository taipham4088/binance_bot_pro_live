from backend.analytics.metrics_engine import MetricsEngine

metrics = MetricsEngine()

print("TOTAL TRADES:", metrics.total_trades())

print("WIN RATE:", metrics.win_rate())

print("AVG WIN:", metrics.avg_win())

print("AVG LOSS:", metrics.avg_loss())

print("PROFIT FACTOR:", metrics.profit_factor())

print("SUMMARY:", metrics.summary())