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
        # Same-side size drop from ACCOUNT/POSITION before ORDER_TRADE_UPDATE (R may be false on MARKET reduce)
        self._post_stream_reduce_guard = {}
        self._post_stream_reduce_guard_ttl = 3.0

    def _position_side_size(self, symbol: str):
        for p in self.position.get_all():
            if p.symbol == symbol:
                return p.side, float(p.size)
        return None

    def _register_same_side_reduction(
        self, symbol: str, side: str, old_sz: float, new_sz: float
    ) -> None:
        if old_sz <= new_sz + 1e-12:
            return
        min_sz = self._get_symbol_min_size(symbol)
        tol = max(min_sz * 0.001, 1e-10, old_sz * 1e-8)
        g = self._post_stream_reduce_guard.get(symbol)
        anchor_old = float(old_sz)
        if (
            g
            and g.get("side") == side
            and abs(float(g["new_sz"]) - anchor_old) <= tol
        ):
            anchor_old = float(g["old_sz"])
        self._post_stream_reduce_guard[symbol] = {
            "side": side,
            "old_sz": anchor_old,
            "new_sz": float(new_sz),
            "mono": time.monotonic(),
        }

    def _prune_stale_reduce_guards(self) -> None:
        now = time.monotonic()
        ttl = self._post_stream_reduce_guard_ttl
        for sym in list(self._post_stream_reduce_guard.keys()):
            if now - self._post_stream_reduce_guard[sym]["mono"] > ttl:
                del self._post_stream_reduce_guard[sym]

    def _consume_stream_reduce_reverse_skip(
        self,
        *,
        symbol: str,
        order_side: str,
        qty: float,
        old_pos,
        eps: float,
    ) -> bool:
        """
        True if ORDER_TRADE_UPDATE should not run single-fill reverse: stream already
        applied the reduce (MARKET reduce often has R=false).
        """
        self._prune_stale_reduce_guards()
        g = self._post_stream_reduce_guard.get(symbol)
        if not g or not old_pos:
            return False
        if time.monotonic() - g["mono"] > self._post_stream_reduce_guard_ttl:
            return False
        if g["side"] != old_pos.side:
            return False
        if not self._fill_opposite_to_position(order_side, old_pos.side):
            return False
        osz = float(old_pos.size)
        min_sz = self._get_symbol_min_size(symbol)
        sz_tol = max(eps * 50, min_sz * 0.01, 1e-7, osz * 1e-6)
        if abs(float(g["new_sz"]) - osz) > sz_tol:
            return False
        reduced = float(g["old_sz"]) - float(g["new_sz"])
        if reduced <= 1e-12:
            return False
        q_tol = max(1e-6, min_sz * 0.01, qty * 1e-5)
        if abs(reduced - qty) > q_tol:
            return False
        del self._post_stream_reduce_guard[symbol]
        return True

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
        self._post_stream_reduce_guard.clear()
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
                    sym = ip.symbol
                    before = self._position_side_size(sym)
                    status, pos = self.position.apply_event(ip)
                    after = self._position_side_size(sym)

                    if status == "UPDATED" and before and after:
                        bs, bz = before
                        a_s, az = after
                        if bs == a_s and az < bz - max(
                            1e-12, self._get_symbol_min_size(sym) * 1e-9
                        ):
                            self._register_same_side_reduction(sym, bs, bz, az)
                    elif status == "CLOSED" and isinstance(pos, dict):
                        ps = float(pos.get("previous_size", 0) or 0)
                        sd = pos.get("side")
                        if ps > 1e-8 and sd:
                            self._register_same_side_reduction(sym, sd, ps, 0.0)

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
                # 🔥 Force close when exchange reports flat
                if size == 0 and old_pos:
                    side = old_pos.side

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

                if status == "UPDATED" and old_pos and old_pos.side == side:
                    if size < float(old_pos.size) - max(
                        1e-12, self._get_symbol_min_size(symbol) * 1e-9
                    ):
                        self._register_same_side_reduction(
                            symbol, old_pos.side, float(old_pos.size), size
                        )
                elif status == "CLOSED" and old_pos:
                    self._register_same_side_reduction(
                        symbol, old_pos.side, float(old_pos.size), 0.0
                    )

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
                            "ts": time.time(),
                            "client_order_id": execution_id,
                            "order_id": str(o.get("i")) if o.get("i") is not None else None,
                        })

                        old_pos_ro = None
                        for p in self.position.get_all():
                            if p.symbol == symbol:
                                old_pos_ro = p
                                break
                        self._apply_position_net_after_opposite_fill(
                            symbol=symbol,
                            order_side=side,
                            qty=qty,
                            price=price,
                            old_pos=old_pos_ro,
                            reduce_only=True,
                        )

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
                        "ts": now,
                        "client_order_id": execution_id,
                        "order_id": str(o.get("i")) if o.get("i") is not None else None,
                    })

                    print("[SYNC] EXECUTION EVENT:", symbol, side, qty, price)
                    from execution.sync.models import PositionState

                    # Opposite-side fill: sync full/partial close or single-fill reverse (not only reduce_only)
                    if old_pos and self._fill_opposite_to_position(side, old_pos.side):
                        self._apply_position_net_after_opposite_fill(
                            symbol=symbol,
                            order_side=side,
                            qty=qty,
                            price=price,
                            old_pos=old_pos,
                        )
                        return

                    current_pos = None
                    for p in self.position.get_all():
                        if p.symbol == symbol:
                            current_pos = p
                            break

                    already_flat = (
                        current_pos is None or
                        current_pos.size == 0
                    )

                    min_s = self._get_symbol_min_size(symbol)
                    if already_flat and qty > min_s * 0.5:
                        op = PositionState(
                            symbol=symbol,
                            side="LONG" if side == "BUY" else "SHORT",
                            size=qty,
                            entry_price=price,
                            unrealized_pnl=0,
                            leverage=0,
                            last_update=time.time()
                        )
                        status, pos = self.position.apply_event(op)
                        if status == "UPDATED":
                            self.bus.publish(PositionUpdated(pos))
                    elif not already_flat:

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

    def _fill_opposite_to_position(self, order_side: str, pos_side: str) -> bool:
        """True if this order side reduces/closes the given position side (one-way futures)."""
        return (pos_side == "LONG" and order_side == "SELL") or (
            pos_side == "SHORT" and order_side == "BUY"
        )

    def _apply_position_net_after_opposite_fill(
        self,
        *,
        symbol: str,
        order_side: str,
        qty: float,
        price: float,
        old_pos,
        reduce_only: bool = False,
    ) -> None:
        """
        Update PositionEngine after a fill on the side that closes/reduces current exposure.
        Handles full close, partial reduce, and single-fill reverse (qty > old size → net flip).
        """
        from execution.sync.models import PositionState

        if not old_pos:
            return

        min_sz = self._get_symbol_min_size(symbol)
        eps = max(min_sz * 0.01, 1e-12)

        if not self._fill_opposite_to_position(order_side, old_pos.side):
            return

        osz = float(old_pos.size)

        # Reduce-only: never run single-fill reverse. If POSITION_UPDATE / ACCOUNT_UPDATE ran
        # before ORDER_TRADE_UPDATE, osz is already the remainder while qty is the fill (e.g.
        # SHORT 0.025 + z=0.05) — qty > osz must not open the opposite leg.
        if reduce_only and qty > osz + eps:
            return

        # MARKET manual reduce often has R=false; stream may already hold post-reduce size.
        if qty > osz + eps and self._consume_stream_reduce_reverse_skip(
            symbol=symbol,
            order_side=order_side,
            qty=qty,
            old_pos=old_pos,
            eps=eps,
        ):
            return

        # Single fill closes old and opens opposite (e.g. SHORT 0.045 + BUY 0.055 → LONG 0.01)
        if qty > osz + eps:
            net = max(0.0, round(qty - osz, 8))
            new_side = "LONG" if order_side == "BUY" else "SHORT"
            z = PositionState(
                symbol=symbol,
                side=old_pos.side,
                size=0.0,
                entry_price=float(old_pos.entry_price or 0),
                unrealized_pnl=0.0,
                leverage=float(old_pos.leverage or 0),
                last_update=time.time(),
            )
            st, meta = self.position.apply_event(z)
            if st == "CLOSED" and meta:
                self.bus.publish(
                    PositionClosed(meta.get("symbol"), meta.get("side"))
                )
            np = PositionState(
                symbol=symbol,
                side=new_side,
                size=net,
                entry_price=float(price),
                unrealized_pnl=0.0,
                leverage=0.0,
                last_update=time.time(),
            )
            st2, pos2 = self.position.apply_event(np)
            if st2 == "UPDATED":
                self.bus.publish(PositionUpdated(pos2))
            return

        # Full close (within tick tolerance)
        if abs(qty - osz) <= max(eps, osz * 1e-9):
            z = PositionState(
                symbol=symbol,
                side=old_pos.side,
                size=0.0,
                entry_price=float(old_pos.entry_price or 0),
                unrealized_pnl=0.0,
                leverage=float(old_pos.leverage or 0),
                last_update=time.time(),
            )
            st, meta = self.position.apply_event(z)
            if st == "CLOSED" and meta:
                self.bus.publish(
                    PositionClosed(meta.get("symbol"), meta.get("side"))
                )
            return

        # Partial reduce only
        new_sz = max(0.0, round(osz - qty, 8))
        EPS = 1e-8
        if new_sz < EPS:
            z = PositionState(
                symbol=symbol,
                side=old_pos.side,
                size=0.0,
                entry_price=float(old_pos.entry_price or 0),
                unrealized_pnl=0.0,
                leverage=float(old_pos.leverage or 0),
                last_update=time.time(),
            )
            st, meta = self.position.apply_event(z)
            if st == "CLOSED" and meta:
                self.bus.publish(
                    PositionClosed(meta.get("symbol"), meta.get("side"))
                )
            return

        rp = PositionState(
            symbol=symbol,
            side=old_pos.side,
            size=new_sz,
            entry_price=None,
            unrealized_pnl=0.0,
            leverage=float(old_pos.leverage or 0),
            last_update=time.time(),
        )
        st, pos = self.position.apply_event(rp)
        if st == "UPDATED":
            self.bus.publish(PositionUpdated(pos))
    
    def get_last_update_ts(self):
        return self.last_update_ts


