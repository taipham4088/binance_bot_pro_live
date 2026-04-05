import asyncio
import time
from .account_engine import AccountEngine
from .position_engine import PositionEngine
from .order_engine import OrderEngine
from .events import *

from execution.adapter.binance import mapper
from execution.state.freeze import ExecutionFreeze
from execution.state.schema_guard import SchemaGuard


class SyncEngine:

    def __init__(self, event_bus, logger, exchange=None):
        self.account = AccountEngine()
        self.position = PositionEngine()
        print("SYNC POSITION ENGINE:", id(self.position))
        self._fee_buffer = {}
        self.order = OrderEngine()
        self.bus = event_bus
        self.logger = logger
        self._last_exec_emit = {}
        self._latency_buffer = {}
        self.freezer = ExecutionFreeze()
        self.guard = SchemaGuard(self.freezer, self._alert)
        self.last_update_ts = None
        self._bootstrapped = False
        self._external_close_handler = None
        self._last_manual_close_emit = {}
        self._manual_close_dedup_sec = 2.0
        self.exchange = exchange
        # 🔥 pending manual close after fill
        self._pending_manual_close = {}
        # reverse expected guard
        self._expected_reverse = {}
        

    def register_signal(self, symbol, execution_id, signal_time, order_sent_time):
        key = f"{symbol}-{execution_id}"

        self._latency_buffer[key] = {
            "signal_time": signal_time,
            "order_sent_time": order_sent_time
        }

        print("🔥 SIGNAL REGISTERED:", key)

    def update_order_sent(self, symbol, execution_id, order_sent_time):

        key = f"{symbol}-{execution_id}"

        if key in self._latency_buffer:
            self._latency_buffer[key]["order_sent_time"] = order_sent_time

            print("🔥 ORDER SENT UPDATED:", key)

    def migrate_execution_id(self, symbol, old_id, new_id):

        old_key = f"{symbol}-{old_id}"
        new_key = f"{symbol}-{new_id}"

        if old_key in self._latency_buffer:
            self._latency_buffer[new_key] = self._latency_buffer.pop(old_key)

        print("🔥 LATENCY ID MIGRATED:", old_key, "→", new_key)

    # ======================
    # ALERT HOOK
    # ======================

    def _alert(self, reason, raw):
        if self.logger:
            self.logger.log("SCHEMA_VIOLATION", {
                "reason": reason,
                "raw": raw
            })
        else:
            print("[SCHEMA_VIOLATION]", reason)

    def set_external_close_handler(self, handler):
        self._external_close_handler = handler

    def _emit_manual_close(self, close_meta: dict):
        if not self._external_close_handler:
            return

        symbol = close_meta.get("symbol")
        if not symbol:
            return

        now = time.time()
        last_ts = self._last_manual_close_emit.get(symbol, 0)
        if now - last_ts < self._manual_close_dedup_sec:
            return

        self._last_manual_close_emit[symbol] = now

        try:
            self._external_close_handler(
                symbol=symbol,
                side=close_meta.get("side"),
                size=close_meta.get("previous_size", 0),
                price=close_meta.get("close_price", 0),
                reason="manual_close_detected",
                source="external",
            )
        except Exception as e:
            print("[SYNC] external close handler error:", e)

    # ======================
    # BOOTSTRAP
    # ======================

    def bootstrap(self, snapshot):

        balances = [
            self.guard.guard("BALANCE_SNAPSHOT", b, lambda x: mapper.map_balance(x))
            for b in snapshot["balances"]
        ]

        positions = [
            self.guard.guard("POSITION_SNAPSHOT", p, lambda x: mapper.map_position(x))
            for p in snapshot["positions"]
        ]

        orders = [
            self.guard.guard("ORDER_SNAPSHOT", o, lambda x: mapper.map_order(x))
            for o in snapshot["orders"]
        ]

        state = self.account.apply_balance_snapshot(balances)
        self.bus.publish(AccountUpdated(state))

        self.position.apply_snapshot(positions)
        # 🔥 EMIT SNAPSHOT POSITIONS
        for pos in self.position.get_all():
            self.bus.publish(PositionUpdated(pos))

        self.order.apply_snapshot(orders)
        self.last_update_ts = time.time()
        self._bootstrapped = True

    # ======================
    # USER STREAM HANDLER
    # ======================

    def on_user_event(self, msg: dict):
        print("📡 SYNC ENGINE RECEIVED:", msg)
        if not self._bootstrapped:
            return
        if self.freezer.is_frozen():
            return      
        
        print("SYNC_ENGINE SELF ID (ws):", id(self))
        print("SYNC ENGINE RECEIVED:", msg.get("e"))
        self.last_update_ts = time.time()
        etype = msg.get("e")

        # ===== ACCOUNT UPDATE =====
        if etype == "ACCOUNT_UPDATE":

            def _handle_account_update(m):

                # balances
                for b in m["a"]["B"]:
                    balance = mapper.map_balance(b)
                    state = self.account.apply_balance_event(balance)
                    self.bus.publish(AccountUpdated(state))

                # positions
                for p in m["a"]["P"]:
                    ip = mapper.map_position(p)
                    status, pos = self.position.apply_event(ip)

                    if status == "UPDATED":
                        self.bus.publish(PositionUpdated(pos))
                    elif status == "CLOSED":
                        closed_symbol = pos.get("symbol") if isinstance(pos, dict) else ip.symbol
                        closed_side = pos.get("side") if isinstance(pos, dict) else ip.side

                        print("🔥 MANUAL CLOSE DETECTED:", closed_symbol)

                        self.bus.publish(PositionClosed(closed_symbol, closed_side))
                        if isinstance(pos, dict):
                            self._emit_manual_close(pos)

            # 🔥 GUARD TOÀN BỘ SCHEMA + MAPPING
            self.guard.guard("ACCOUNT_UPDATE", msg, _handle_account_update)

        # ===== INTERNAL POSITION UPDATE =====
        elif msg.get("type") == "POSITION_UPDATE":

            try:
                symbol = msg.get("symbol")
                side = msg.get("side")
                size = float(msg.get("size", 0))
                # normalize floating drift
                min_size = self._get_symbol_min_size(symbol)
                if abs(size) < min_size * 0.5:
                    size = 0

                # 🔥 cleanup reverse expected timeout
                now = time.time()
                for sym, data in list(self._expected_reverse.items()):
                    if now - data["ts"] > 5:
                        del self._expected_reverse[sym]
                
                # 🔥 OPTION B — AUTO CLOSE MANUAL OPEN

                old_pos = None
                for p in self.position.get_all():
                    if p.symbol == symbol:
                        old_pos = p
                        break
                
                # 🔥 Reverse detect
                manual_reverse = False

                #if old_pos and old_pos.size > 0:

                 #   reverse = (
                  #      (old_pos.side == "LONG" and side == "SHORT") or
                   #     (old_pos.side == "SHORT" and side == "LONG")
                    #)

                    #if reverse:
                     #   manual_reverse = True
                    # mark expected reverse
                    #if reverse:
                     #   self._expected_reverse[symbol] = {
                      #      "side": side,
                       #     "ts": time.time()
                        #}

                manual_open = False
                # 🔥 reverse expected skip
                expected = self._expected_reverse.get(symbol)
                if expected:
                    if expected["side"] == side:
                        print("🛡 EXPECTED REVERSE — skip manual guard:", symbol)
                        del self._expected_reverse[symbol]
                        manual_open = False

                # flat → manual open
                min_size = self._get_symbol_min_size(symbol)

                if (not old_pos or old_pos.size == 0) and size >= min_size:

                    # 🔥 Skip if intent active (reverse / execution)
                    try:
                        intent = None
                        if hasattr(self, "live_execution_system"):
                            intent = getattr(self.live_execution_system, "active_intent", None)

                        if intent:
                            manual_open = False
                        else:
                            manual_open = True

                    except Exception:
                        manual_open = True

                    # 🔥 skip if intent execution
                    try:
                        if hasattr(self, "live_execution_system"):
                            intent = getattr(self.live_execution_system, "active_intent", None)
                            if intent:
                                manual_open = False
                            else:
                                manual_open = True
                        else:
                            manual_open = True
                    except Exception:
                        manual_open = True

                # 🔥 Skip if execution running (prevent partial fill false detect)
                try:
                    if hasattr(self, "live_execution_system"):
                        lock = getattr(self.live_execution_system, "execution_lock", None)
                        if lock and lock.state == "RUNNING":
                            manual_open = False

                except Exception:
                    pass

                # 🔥 Production-safe manual open guard (deterministic)
                if not hasattr(self, "_manual_open_flag"):
                    self._manual_open_flag = {}

                manual_flag = self._manual_open_flag.get(symbol, False)
                # 🔥 Skip if recent execution (reverse protection)
                try:
                    if hasattr(self, "_last_execution_ts"):
                        if time.time() - self._last_execution_ts < 2:
                            manual_open = False
                except Exception:
                    pass

                # skip if execution active
                try:
                    if hasattr(self, "live_execution_system"):
                        lock = getattr(self.live_execution_system, "execution_lock", None)
                        if lock and lock.state == "RUNNING":
                            manual_open = False
                except Exception:
                    pass

                # 🔥 Trigger only once when manual open detected
                if manual_open and not manual_flag:
                    
                    self._manual_open_flag[symbol] = True

                    print("🚨 MANUAL OPEN DETECTED:", symbol, side, size)

                    self._pending_manual_close[symbol] = True
                    print("⏳ AUTO CLOSE PENDING (WAIT FILL):", symbol)

                    return

                # 🔥 Reset flag when position becomes flat
                if size == 0:
                    self._manual_open_flag[symbol] = False
                    self._pending_manual_close.pop(symbol, None)

                from execution.sync.models import PositionState

                p = PositionState(
                    symbol=symbol,
                    side=side,
                    size=size,
                    entry_price=None,   # 🔥 preserve old
                    unrealized_pnl=None,
                    leverage=0,
                    last_update=time.time()
                )
                # ===== REVERSE SAFE =====
                status, pos = self.position.apply_event(p)

                if status == "UPDATED":
                    self.bus.publish(PositionUpdated(pos))

                elif status == "CLOSED":
                    self.bus.publish(
                        PositionClosed(
                            pos.get("symbol"),
                            pos.get("side")
                        )
                    )

            except Exception as e:
                print("⚠ POSITION_UPDATE ERROR:", e)

        # ===== ORDER UPDATE =====
        elif etype == "ORDER_TRADE_UPDATE":

            def _handle_order(m):
                o = mapper.map_order(m["o"])
                order_state = self.order.apply_event(o)
                self.bus.publish(OrderUpdated(order_state))

            self.guard.guard("ORDER_TRADE_UPDATE", msg, _handle_order)

            # 🔥 ===== ADD ĐOẠN NÀY NGAY DƯỚI =====
            try:
                o = msg.get("o", {})
                # ===== ORDER ACK =====
                if o.get("X") == "NEW":

                    execution_id = o.get("c")
                    symbol = o.get("s")

                    key = f"{symbol}-{execution_id}"

                    now = time.time()

                    latency = self._latency_buffer.setdefault(key, {})

                    # fallback signal (sớm hơn)
                    if "signal_time" not in latency:
                        latency["signal_time"] = now - 0.005
                        print("🔥 FALLBACK SIGNAL:", key)

                    # fallback order sent (giữa)
                    if "order_sent_time" not in latency:
                        latency["order_sent_time"] = now - 0.002
                        print("🔥 FALLBACK ORDER SENT:", key)

                    # ack thật
                    latency["exchange_ack_time"] = now

                    print("🔥 ACK RECEIVED:", key)

                if o.get("X") == "FILLED":
                    from backend.analytics.analytics_bus import analytics_bus

                    execution_id = o.get("c")
                    symbol = o.get("s")
                    side = o.get("S")
                    qty = float(o.get("z", 0))
                    price = float(o.get("L", 0))
                    
                    # 🔥 AUTO CLOSE AFTER FILL
                    if self._pending_manual_close.get(symbol):

                        print("🔥 AUTO CLOSE AFTER FILL:", symbol, qty)

                        try:
                            asyncio.create_task(
                                self.live_execution_system.close_manual_position(
                                    symbol,
                                    qty,
                                    "LONG" if side == "BUY" else "SHORT"
                                )
                            )
                        except Exception as e:
                            print("❌ AUTO CLOSE AFTER FILL ERROR:", e)

                        self._pending_manual_close[symbol] = False

                    fee = float(o.get("n", 0))
                    fee_asset = o.get("N")
                    self._fee_buffer.setdefault(execution_id, 0)
                    self._fee_buffer[execution_id] += fee

                    r_flag = o.get("R", False)
                    reduce_only = r_flag is True or (
                        isinstance(r_flag, str) and r_flag.lower() in ("true", "1")
                    )

                    if reduce_only:
                        print("[SYNC] REDUCE ONLY CLOSE:", symbol, side, qty)
                        # mark execution timestamp
                        self._last_execution_ts = time.time()

      
                        # emit execution close
                        print("[SYNC] EXECUTION EVENT:", symbol, side, qty, price)
                        total_fee = round(self._fee_buffer.pop(execution_id, fee), 3)
                        analytics_bus.publish("EXECUTION", {
                            "symbol": symbol,
                            "side": "LONG" if side == "BUY" else "SHORT",
                            "execution_type": "CLOSE",
                            "size": qty,
                            "signal_price": price,
                            "fill_price": price,
                            "signal_time": time.time(),
                            "order_sent_time": time.time(),
                            "exchange_ack_time": time.time(),
                            "fill_time": time.time(),
                            "fee": total_fee,            
                            "fee_asset": fee_asset
                        })
                        # emit close analytics
                        analytics_bus.publish("TRADE", {
                            "symbol": symbol,
                            "side": "LONG" if side == "BUY" else "SHORT",
                            "execution_type": "CLOSE",
                            "price": price,
                            "size": qty,
                            "fee": total_fee,              
                            "fee_asset": fee_asset, 
                            "pnl": float(o.get("rp", 0)),
                            "ts": time.time()
                        })

                        return

                    key = f"{symbol}-{execution_id}"

                    if key in self._last_exec_emit:
                        return

                    self._last_exec_emit[key] = time.time()
                    # 🔥 snapshot old position
                    old_pos = None
                    for p in self.position.get_all():
                        if p.symbol == symbol:
                            old_pos = p
                            break
                    # 🔥 detect reverse / manual close
                    if old_pos and (
                        (old_pos.side == "LONG" and side == "SELL") or
                        (old_pos.side == "SHORT" and side == "BUY")
                    ):
                        self.bus.publish(
                            PositionClosed(
                                old_pos.symbol,
                                old_pos.side
                            )
                        )

                    now = time.time()
                    latency = self._latency_buffer.get(key, {})
                    print("🔥 LATENCY LOOKUP:", key)
                    print("🔥 LATENCY FOUND:", latency)

                    total_fee = round(self._fee_buffer.pop(execution_id, fee), 3)
                    analytics_bus.publish("EXECUTION", {
                        "symbol": symbol,
                        "side": "LONG" if side == "BUY" else "SHORT",
                        "size": qty,

                        "signal_price": price,
                        "fill_price": price,

                        # 🔥 add real timestamps
                        "signal_time": latency.get("signal_time", now),
                        "order_sent_time": latency.get("order_sent_time", now),
                        "exchange_ack_time": latency.get("exchange_ack_time", now),
                        "fill_time": now,
                        "fee": total_fee,
                        "fee_asset": fee_asset
                    })
                    # 🔥 THÊM NGAY TẠI ĐÂY
                    analytics_bus.publish("TRADE", {
                        "symbol": symbol,
                        "side": "LONG" if side == "BUY" else "SHORT",
                        "price": price,
                        "size": qty,
                        "fee": total_fee,
                        "fee_asset": fee_asset,
                        "pnl": 0,
                        "ts": now
                    })

                    print("[SYNC] EXECUTION EVENT:", symbol, side, qty, price)
                    from execution.sync.models import PositionState
                    # 🔥 Detect reduce / close safely (prevent phantom)
                    manual_reduce = False
                    manual_close = False

                    if old_pos:

                        opposite = (
                            (old_pos.side == "LONG" and side == "SELL") or
                            (old_pos.side == "SHORT" and side == "BUY")
                        )

                        # full close
                        if opposite and qty == old_pos.size:
                            manual_close = True
                            print("🔥 MANUAL CLOSE DETECTED — skip phantom position")

                        # partial reduce (do NOT skip — let POSITION_UPDATE handle remaining)
                        elif opposite and qty < old_pos.size:
                            manual_reduce = True
                            print("🔥 MANUAL REDUCE DETECTED — allow remaining position")

                        # 🔥 Skip only full close
                        if manual_close:
                            return

                    # 🔥 Only apply position if not manual reduce / close / already flat
                    current_pos = None
                    for p in self.position.get_all():
                        if p.symbol == symbol:
                            current_pos = p
                            break

                    already_flat = (
                        current_pos is None or
                        current_pos.size == 0
                    )

                    if not manual_reduce and not manual_close and not already_flat:

                        p = PositionState(
                            symbol=symbol,
                            side="LONG" if side == "BUY" else "SHORT",
                            size=qty,
                            entry_price=price,
                            unrealized_pnl=0,
                            leverage=0,
                            last_update=time.time()
                        )

                        status, pos = self.position.apply_event(p)

                        if status == "UPDATED":
                            self.bus.publish(PositionUpdated(pos))

            except Exception as e:
                print("⚠ SYNC EXECUTION ERROR:", e)

        
    # ======================
    # STEP 4 VIEW API
    # ======================

    def get_positions(self):
        """
        Trả toàn bộ position hiện tại (list objects).
        """
        return self.position.get_all()

    def get_open_orders(self):
        """
        Trả toàn bộ open orders hiện tại.
        """
        return self.order.get_open_orders()

    def get_account_state(self):
        """
        Optional: expose account state nếu sau này cần.
        """
        return self.account.state
    
    def _get_symbol_min_size(self, symbol):

        try:
            if hasattr(self, "symbol_precision"):
                info = self.symbol_precision.get(symbol)
                if info:
                    return float(info.get("stepSize", 0.001))
        except Exception:
            pass

        return 0.001
    
    def get_last_update_ts(self):
        return self.last_update_ts


