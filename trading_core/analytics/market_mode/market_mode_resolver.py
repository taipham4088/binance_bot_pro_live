import time
from .market_mode_models import MarketMode, MarketModeState


class MarketModeResolver:

    def resolve(self, *, side_bias, equity_state, volatility=None, trend=None):

        # default
        mode = MarketMode.NEUTRAL
        confidence = 0.3
        reason = "no consensus"

        # --- logic gợi ý (bạn có thể tinh chỉnh dần) ---

        if side_bias in ("LONG", "SHORT") and equity_state == "GROWING":
            mode = MarketMode.LONG if side_bias == "LONG" else MarketMode.SHORT
            confidence = 0.7
            reason = "trend + system growing"

        elif equity_state == "NEUTRAL":
            mode = MarketMode.DUAL
            confidence = 0.6
            reason = "range / dual opportunity"

        elif equity_state == "DRAWDOWN":
            mode = MarketMode.DUAL
            confidence = 0.4
            reason = "defensive / chop"

        return MarketModeState(
            mode=mode,
            side_bias=side_bias,
            confidence=confidence,
            reason=reason,
            ts=int(time.time() * 1000)
        )
