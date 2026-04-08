from backend.control_plane.engine_registry.engine_registry import engine_registry
from trading_core.engines.dual_engine import DualEngine


def dual_engine_factory(config, context, market, execution, account, **kwargs):
    return DualEngine(
        config=config,
        context=context,
        market=market,
        execution_adapter=execution,
        account=account
    )


def _register_if_missing(name, factory):
    # Keep bootstrap idempotent across repeated imports.
    if name not in engine_registry.list_engines():
        engine_registry.register(name, factory)


_register_if_missing("dual_engine", dual_engine_factory)
_register_if_missing("range", dual_engine_factory)
_register_if_missing("trend", dual_engine_factory)
_register_if_missing("momentum", dual_engine_factory)
