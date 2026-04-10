from backend.control_plane.engine_registry.engine_registry import engine_registry
from trading_core.engines.dual_engine import DualEngine


def range_trend_engine_factory(config, context, market, execution, account, **kwargs):
    return DualEngine(
        config=config,
        context=context,
        market=market,
        execution_adapter=execution,
        account=account,
    )


def _register_if_missing(name, factory):
    if name not in engine_registry.list_engines():
        engine_registry.register(name, factory)


# Single production strategy: Range Trend (dual-sided breakout/retest + H1 regime).
_register_if_missing("range_trend", range_trend_engine_factory)
