from dataclasses import dataclass
from backend.execution.base_execution import BaseExecution
import time
from backend.analytics.analytics_bus import analytics_bus


@dataclass
class ExecutionEvent:
    intent_id: str
    decision: str
    reason: str
    ts: int
    symbol: str | None = None
    side: str | None = None
    size: float | None = None

class StubExecution(BaseExecution):
    """
    Phase 3.3 – Execution Stub (Multi-symbol aware)
    """

    def __init__(self, session_id: str, mode: str):
        self.session_id = session_id
        self.mode = mode
        self._external_close_cache = {}

    
    def handle_external_close(
        self,
        *,
        symbol: str,
        side: str | None = None,
        size: float | None = None,
        price: float | None = None,
        reason: str = "manual_close_detected",
        source: str = "external",
    ) -> ExecutionEvent:
        """
        Handle manual/external close from exchange.

        IMPORTANT:
        - MUST NOT go through execute()
        - MUST emit analytics via same path
        """

        size = float(size or 0)
        price = float(price or 0)

        # --- normalize side ---
        if side and side.upper() in ["BUY", "LONG"]:
            normalized_side = "LONG"
        else:
            normalized_side = "SHORT"
        # --- idempotency guard ---
        key = f"{symbol}"

        last = self._external_close_cache.get(key)

        if last and last["size"] == size:
            return None  # skip duplicate

        self._external_close_cache[key] = {
            "size": size,
            "ts": time.time()
        }

        # --- build event ---
        event = ExecutionEvent(
            intent_id=f"external-close-{int(time.time() * 1000)}",
            decision="CLOSED",
            reason=reason,
            ts=int(time.time() * 1000),
            symbol=symbol,
            side=normalized_side,
            size=size,
        )
        # 🔥 EXECUTION EVENT (FIX ĐÚNG)
        try:
            now = time.time()

            analytics_bus.publish("EXECUTION", {
                "symbol": symbol,
                "side": normalized_side,
                "size": size,

                "signal_price": price if price > 0 else None,
                "fill_price": price if price > 0 else None,

                "signal_time": now,
            })
        except Exception as e:
            print("⚠ EXECUTION EVENT ERROR (external):", e)


        # 🔥 POSITION CLOSE
        try:
            analytics_bus.publish("POSITION_CLOSE", {
                "symbol": symbol,
                "side": normalized_side,
                "price": price,
                "size": size,
                "fee": 0,
                "source": source,
            })
        except Exception as e:
            print("⚠ ANALYTICS BUS ERROR (external close):", e)


        # 🔥 ADD TRADE EVENT (QUAN TRỌNG)
        try:
            analytics_bus.publish("TRADE", {
                "symbol": symbol,
                "side": normalized_side,
                "price": price,
                "size": size,
                "pnl": 0,
                "ts": time.time()
            })
        except Exception as e:
            print("⚠ TRADE EVENT ERROR (external):", e)

        return event

    def execute(self, intent) -> ExecutionEvent:
        """
        Simulated execution:
        - OPEN  -> OPENED
        - CLOSE -> CLOSED
        - else  -> NO_TRADE
        """
        print("🔥 STUB EXECUTION CALLED (NEW VERSION)")
        if intent.type == "OPEN":
            decision = "OPENED"
            reason = f"stub_open:{self.mode}"

        elif intent.type == "CLOSE":
            decision = "CLOSED"
            reason = f"stub_close:{self.mode}"

        else:
            decision = "NO_TRADE"
            reason = f"stub_execution:{self.mode}"

        event = ExecutionEvent(
            intent_id=intent.intent_id,
            decision=decision,
            reason=getattr(intent, "reason", reason),
            ts=int(time.time() * 1000),
            symbol=getattr(intent, "symbol", None),
            side=getattr(intent, "side", None),
            size=getattr(intent, "qty", None)
        )

        
        event.source = getattr(intent, "source", "internal")
        event.position = {
            "side": getattr(intent, "side", "").lower(),
            "size": getattr(intent, "qty", 0)
        }


        try:
            if decision == "OPENED":
                open_price = float(getattr(intent, "price", 0) or 0)
                if open_price <= 0:
                    open_price = 1 

                # 🔥 EXECUTION EVENT
                analytics_bus.publish("EXECUTION", {
                    "symbol": event.symbol,
                    "side": event.side,
                    "size": event.size,
                    "signal_price": open_price,
                    "fill_price": open_price,
                    "signal_time": time.time(),
                })

                analytics_bus.publish("POSITION_OPEN", {
                    "symbol": event.symbol,
                    "side": event.side,
                    "price": open_price,
                    "size": event.size,
                    "fee": 0,
                    "source": event.source,
                })
                # 🔥 ADD TRADE EVENT (NGAY DƯỚI POSITION_OPEN)
                analytics_bus.publish("TRADE", {
                    "symbol": event.symbol,
                    "side": event.side,
                    "price": open_price,
                    "size": event.size,
                    "pnl": 0,
                    "ts": time.time()
                })

            elif decision == "CLOSED":

                close_price = getattr(intent, "price", 0) or 0

                # 🔥 EXECUTION EVENT
                analytics_bus.publish("EXECUTION", {
                    "symbol": event.symbol,
                    "side": event.side,
                    "size": event.size,
                    "signal_price": close_price,
                    "fill_price": close_price,
                    "signal_time": time.time(),
                })
                
                analytics_bus.publish("POSITION_CLOSE", {
                    "symbol": event.symbol,
                    "side": event.side,
                    "price": getattr(intent, "price", 0) or 0,
                    "size": event.size,
                    "fee": 0,
                    "source": event.source,
                })
                # 🔥 ADD TRADE EVENT (NGAY DƯỚI POSITION_CLOSE)
                analytics_bus.publish("TRADE", {
                    "symbol": event.symbol,
                    "side": event.side,
                    "price": getattr(intent, "price", 0) or 0,
                    "size": event.size,
                    "pnl": 0,
                    "ts": time.time()
                })

        except Exception as e:
            print("⚠ ANALYTICS BUS ERROR:", e)
        # ✅ QUAN TRỌNG NHẤT
        return event
