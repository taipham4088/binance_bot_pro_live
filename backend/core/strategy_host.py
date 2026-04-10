from trading_core.runtime.context import RuntimeContext
from backend.control_plane.engine_registry.engine_registry import engine_registry
import backend.engines.dual_engine_registration
from backend.runtime.runtime_config import runtime_config

_LEGACY_STRATEGY_KEYS = frozenset({"range", "trend", "momentum", "dual_engine"})


def normalize_strategy_engine_key(name: str | None) -> str:
    n = (name or "range_trend").strip().lower()
    if n in _LEGACY_STRATEGY_KEYS:
        return "range_trend"
    if n == "range_trend":
        return "range_trend"
    return "range_trend"


class StrategyHost:

    def create_engine(self,
                      config,
                      market,
                      execution,
                      account):

        context = RuntimeContext(config)

        engine_type = normalize_strategy_engine_key(
            runtime_config.get(
                "strategy",
                getattr(config, "engine", "range_trend"),
            )
        )
        symbol = (
            getattr(config, "symbol", None)
            or runtime_config.get("symbol", "BTCUSDT")
        )

        engine = engine_registry.create_engine(
            engine_type,
            config=config,
            context=context,
            market=market,
            execution=execution,
            account=account,
            symbol=symbol,
        )

        return engine
