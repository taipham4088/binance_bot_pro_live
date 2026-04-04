from backend.control_plane.engine_registry.engine_registry import engine_registry
from trading_core.engines.dual_engine import DualEngine


def dual_engine_factory(config, context, market, execution, account):
    return DualEngine(
        config=config,
        context=context,
        market=market,
        execution=execution,
        account=account
    )


engine_registry.register(
    "dual_engine",
    dual_engine_factory
)
