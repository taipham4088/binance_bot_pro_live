from .intent_schema import IntentType
from .target_state import TargetState


class QuantityPolicy:
    """
    Map ExecutionIntent -> TargetState (symbol, side, qty)

    Target must be self-contained for execution layer.
    """
    def _get_step_size(self, symbol):

        try:
            import requests

            if not hasattr(self, "_exchange_info"):
                url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
                self._exchange_info = requests.get(url).json()

            for s in self._exchange_info["symbols"]:
                if s["symbol"] == symbol:
                    for f in s["filters"]:
                        if f["filterType"] == "LOT_SIZE":
                            return float(f["stepSize"])

        except Exception as e:
            print("[STEP SIZE ERROR]", e)

        return 0.001

    def map_intent_to_target(self, intent, current_net):

        if intent is None:
            raise ValueError("INTENT_REQUIRED")

        if hasattr(intent, "validate_schema"):
            intent.validate_schema()

        # ===== SET FLAT =====
        if intent.type == IntentType.SET_FLAT:
            return TargetState(
                symbol=intent.symbol,
                side="FLAT",
                qty=0.0
            )

        # ===== SET POSITION =====
        if intent.type == IntentType.SET_POSITION:

            side = intent.side
            qty = intent.qty

            if side not in ("LONG", "SHORT"):
                raise ValueError("INVALID_SIDE")

            if qty is None:
                raise ValueError("QTY_REQUIRED")

            try:
                qty = float(qty)
            except Exception:
                raise ValueError("QTY_NOT_NUMBER")

            if qty <= 0:
                raise ValueError("QTY_MUST_BE_POSITIVE")

            # =========================
            # NORMALIZE STEP SIZE
            # =========================
            try:
                import math

                step = self._get_step_size(intent.symbol)

                qty = math.floor(qty / step) * step

                # tránh float drift
                qty = float(f"{qty:.10f}")

            except Exception as e:
                print("[QUANTITY NORMALIZE ERROR]", e)

            return TargetState(
                symbol=intent.symbol,
                side=side,
                qty=qty
            )

        raise ValueError(f"INTENT_NOT_SUPPORTED: {intent.type}")
