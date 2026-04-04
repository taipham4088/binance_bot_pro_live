from backend.analytics.trade_journal import TradeJournal
from backend.analytics.pnl_engine import PnLEngine
from backend.analytics.metrics_engine import MetricsEngine
from backend.analytics.dashboard_cache import DashboardCache


class DummyStateEngine:

    def get_position_state(self):
        return {"side": "long", "size": 0.01}


journal = TradeJournal()

pnl = PnLEngine()

metrics = MetricsEngine()

state = DummyStateEngine()


cache = DashboardCache(
    state_engine=state,
    pnl_engine=pnl,
    metrics_engine=metrics,
    trade_journal=journal
)


print(cache.get())