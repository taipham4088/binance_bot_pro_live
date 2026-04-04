from dotenv import load_dotenv
load_dotenv()

from backend.execution.stub_execution import StubExecution
from binance import Client
import os
import time
from backend.execution.decision.decision_types import ExecutionPlanType


class ShadowExecution(StubExecution):

    def __init__(self, session_id: str, mode: str, session=None):
        super().__init__(session_id, mode)

        self.session = session

        # BINANCE TESTNET CLIENT
        self.client = Client(
            os.getenv("BINANCE_API_KEY"),
            os.getenv("BINANCE_API_SECRET"),
            testnet=True
        )

        self.client.FUTURES_URL = "https://testnet.binancefuture.com/fapi"

        # sync server time
        self.sync_time()

    def sync_time(self):
        server_time = self.client.get_server_time()["serverTime"]
        local_time = int(time.time() * 1000)
        self.client.TIME_OFFSET = server_time - local_time

    # =========================================================
    # GET CURRENT POSITION FROM EXCHANGE
    # =========================================================

    def _get_current_position(self, symbol: str):

        try:
            positions = self.client.futures_position_information()

            for p in positions:
                if p["symbol"] == symbol:

                    amt = float(p["positionAmt"])

                    if abs(amt) < 1e-8:
                        return None

                    if amt > 0:
                        return {"side": "LONG", "size": abs(amt)}
                    else:
                        return {"side": "SHORT", "size": abs(amt)}

        except Exception as e:
            print("❌ POSITION FETCH ERROR:", e)

        return None

    # =========================================================
    # EXECUTE
    # =========================================================

    def execute(self, decision, *args, **kwargs):
       
        symbol = "BTCUSDT"
        fill_price = 0
        fill_qty = 0
        side = None

        try:

            print("DEBUG EXEC TYPE:", type(decision))
            print("DEBUG EXEC VALUE:", decision)
            
            from backend.execution.decision.decision_types import ExecutionPlanType
            plan = decision.plan    
            from backend.observability.execution_monitor_instance import execution_monitor
            print("🔥 SHADOW MONITOR:", id(execution_monitor))

            trace_key = execution_monitor.start_trace(
                symbol=symbol,
                side="LONG" if plan.side.value == "long" else "SHORT",
                size=float(plan.quantity),
                signal_price=None
            )

            execution_monitor.mark_order_sent(trace_key)

            action = getattr(plan, "action", None)
            if hasattr(action, "value"):
                action = action.value
            if isinstance(action, str):
                action = {
                    "OPEN": ExecutionPlanType.OPEN_POSITION,
                    "CLOSE": ExecutionPlanType.CLOSE_POSITION,
                    "REDUCE": ExecutionPlanType.REDUCE_ONLY,
                    "NOOP": ExecutionPlanType.NOOP,
                    "BLOCK": ExecutionPlanType.BLOCK,
                }.get(action, action)

            if action == ExecutionPlanType.NOOP:

                print("🟡 SHADOW: NOOP")

                # return fake execution event
                from backend.core.execution_models import ExecutionEvent

                return ExecutionEvent(
                    intent_id=f"noop-{int(time.time()*1000)}",
                    decision="NOOP",
                    reason="already in desired state",
                    ts=int(time.time()*1000),
                    symbol=plan.symbol,
                    side=None,
                    size=0
                )

            print("PLAN ACTION:", action)

            # =========================
            # OPEN POSITION
            # =========================

            if action == ExecutionPlanType.OPEN_POSITION:

                side = "BUY" if plan.side.value == "long" else "SELL"
                quantity = float(plan.quantity)

                print(f"🔵 SHADOW REAL OPEN → {symbol} {side} {quantity}")

                response = self.client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type="MARKET",
                    quantity=quantity
                )
                execution_monitor.mark_exchange_ack(trace_key)
                # ===== exchange acknowledged =====
                
                order_id = response["orderId"]

                time.sleep(0.3)

                order_info = self.client.futures_get_order(
                    symbol=symbol,
                    orderId=order_id
                )

                print("DEBUG ORDER:", order_info)

                fill_price = float(order_info.get("avgPrice", 0))
                fill_qty = float(order_info.get("executedQty", quantity))
                if execution_monitor.last_trace and execution_monitor.last_trace.fill_time is None:
                    execution_monitor.mark_fill(trace_key, fill_price)
                print("DEBUG OPEN PRICE:", fill_price)
                # ===== Execution Monitor: fill =====
                
                print(f"🟢 SHADOW FILLED → price={fill_price} qty={fill_qty}")

            # =========================
            # CLOSE POSITION
            # =========================

            elif action == ExecutionPlanType.CLOSE_POSITION:

                current = self._get_current_position(symbol)

                if not current:
                    print("🟡 SHADOW: no position to close")
                    return

                side = "SELL" if current["side"] == "LONG" else "BUY"

                print(f"🔵 SHADOW REAL CLOSE → {symbol} {side} {current['size']}")

                response = self.client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type="MARKET",
                    quantity=current["size"],
                    reduceOnly=True
                )

                print("🟢 SHADOW CLOSE RESPONSE:", response.get("status"))

                fill_qty = current["size"]
                # lấy giá thị trường làm exit price
                ticker = self.client.futures_mark_price(symbol=symbol)
                fill_price = float(ticker["markPrice"])

                print("DEBUG CLOSE PRICE:", fill_price)

            else:

                print("🟡 SHADOW: unsupported plan", action)
                return

        except Exception as e:

            print("❌ SHADOW REAL ERROR:", e)

        # =========================================================
        # BUILD PAPER INTENT
        # =========================================================

        class StubIntent:
            pass

        paper_intent = StubIntent()

        paper_intent.intent_id = f"plan-{int(time.time()*1000)}"
        paper_intent.symbol = symbol
        paper_intent.price = fill_price
        # ===== FIX LATENCY TIMESTAMP =====
        paper_intent.ts = int(time.time() * 1000)

        # ===== LẤY POSITION 1 LẦN DUY NHẤT =====
        pos = self._get_current_position(symbol)

        # ===== FIX QUAN TRỌNG =====
        paper_intent.qty = pos["size"] if pos else fill_qty

        if side == "BUY":
            paper_intent.side = "LONG"
        elif side == "SELL":
            paper_intent.side = "SHORT"
        else:
            paper_intent.side = "FLAT"

        # ===== POSITION SNAPSHOT =====
        if pos:
            paper_intent.position = {
                "side": (pos.get("side") or "flat").lower(),
                "size": pos["size"]
            }
        else:
            paper_intent.position = {
                "side": "flat",
                "size": 0
            }

        # =========================================================
        # SYNC POSITION FROM EXCHANGE (SOURCE OF TRUTH)
        # =========================================================

        pos = self._get_current_position(symbol)

        if pos is None:
            paper_intent.type = "CLOSE"

        else:

            paper_intent.type = "OPEN"

            if pos["side"] == "SHORT":
                paper_intent.side = "SHORT"
            else:
                paper_intent.side = "LONG"

            paper_intent.qty = pos["size"]

        # =========================================================
        # EXECUTE PAPER EVENT
        # =========================================================

        paper_result = super().execute(paper_intent)

        if paper_result is None:
            print("❌ paper_result is None → create fallback")

            from backend.core.execution_models import ExecutionEvent

            paper_result = ExecutionEvent(
                intent_id=paper_intent.intent_id,
                decision="UNKNOWN",
                reason="fallback",
                ts=int(time.time()*1000),
                symbol=symbol,
                side=paper_intent.side,
                size=paper_intent.qty
            )
        
        # ===== SYNC POSITION INTO EXECUTION STATE =====
        try:

            pos = self._get_current_position(symbol)

            if self.session and hasattr(self.session, "engine"):

                engine = self.session.engine

                if hasattr(engine, "execution_state"):

                    state = engine.execution_state

                    if pos:
                        state.position.side = (pos.get("side") or "flat").lower()
                        state.position.size = pos["size"]
                    else:
                        state.position.side = "flat"
                        state.position.size = 0

        except Exception as e:
            print("⚠ POSITION SYNC ERROR:", e)
        # ===== SYNC POSITION DIRECTLY FROM EXCHANGE =====
        pos = self._get_current_position(symbol)
        print("DEBUG POS AFTER EXEC:", pos)
        if pos is None:
            print("🔥 POSITION CLOSED (SYNC)")
        
        #==================================================
        if pos:
            paper_result.position = {
                "side": (pos.get("side") or "flat").lower(),
                "size": pos["size"]
            }

        # attach position for timeline reducer

        if pos:
            position_data = {
                "side": (pos.get("side") or "flat").lower(),
                "size": pos["size"]
            }
        else:
            position_data = {
                "side": "flat",
                "size": 0
            }

        if paper_result:
            paper_result.position = position_data
            paper_result.payload = {"position": position_data}

        print("🟡 SHADOW PAPER RESULT:", paper_result.decision)

        return paper_result