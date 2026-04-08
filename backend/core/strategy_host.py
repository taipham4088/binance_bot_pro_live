from trading_core.runtime.context import RuntimeContext
from backend.control_plane.engine_registry.engine_registry import engine_registry
import backend.engines.dual_engine_registration
from backend.runtime.runtime_config import runtime_config

class StrategyHost:

    def create_engine(self,
                      config,
                      market,
                      execution,
                      account):

        context = RuntimeContext(config)

        engine_type = runtime_config.get(
            "strategy",
            getattr(config, "engine", "dual_engine")
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
            symbol=symbol
        )

        return engine
