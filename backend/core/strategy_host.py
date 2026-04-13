from trading_core.runtime.context import RuntimeContext
from trading_core.data.range_trend_profiles import normalize_range_trend_engine_key
from backend.control_plane.engine_registry.engine_registry import engine_registry
import backend.engines.dual_engine_registration
from backend.runtime.runtime_config import runtime_config


def normalize_strategy_engine_key(name: str | None) -> str:
    return normalize_range_trend_engine_key(name)


class StrategyHost:

    def create_engine(self,
                      config,
                      market,
                      execution,
                      account):
        print("[STRATEGY HOST]")
        print("trade_mode =", getattr(config, "trade_mode", None))
        print("[ENGINE CONFIG]")
        print("trade_mode =", getattr(config, "trade_mode", None))
        print("risk =", getattr(config, "risk_per_trade", None))
        print("balance =", getattr(config, "initial_balance", None))
        print("strategy =", getattr(config, "engine", None))
        print("[STRATEGY HOST CONFIG]")
        print("trade_mode =", getattr(config, "trade_mode", None))
        print("risk =", getattr(config, "risk_per_trade", None))
        print("strategy =", getattr(config, "engine", None))

        context = RuntimeContext(config)

        engine_type = normalize_strategy_engine_key(
            getattr(config, "engine", None)
            or runtime_config.get("strategy")
            or "range_trend"
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

        print(
            "[ENGINE CREATE]",
            f"id={id(engine)}",
            f"registry_key={engine_type!r}",
            f"type={type(engine).__name__}",
        )

        return engine
