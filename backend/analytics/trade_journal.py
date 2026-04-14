import sqlite3
import os
import time
import json
import threading
from backend.storage.mode_storage import mode_storage



class TradeJournal:
    # Opposite-side: treat near-equal sizes as full close (avoid Case 2 reverse on float drift)
    REVERSE_FULL_CLOSE_EPS = 1e-6
    TRADE_SIZE_ROUND_DECIMALS = 8
    """
    TradeJournal lưu toàn bộ vòng đời trade.

    Close ingestion: POSITION_CLOSE (handle_event) and TRADE (handle_trade).
    EXECUTION is not handled here — analytics_bus sends it to ExecutionMonitor only.
    """

    def __init__(self, mode="shadow", logical_mode=None):
        """
        mode: storage bucket (e.g. session id: live, live_shadow) — isolates DB/open_trade per session.
        logical_mode: persisted trade.mode / restore match (e.g. api_mode: live vs live_shadow).
        """
        self.mode = mode
        self.logical_mode = logical_mode if logical_mode is not None else mode
        self.db_path = mode_storage.get_trade_path(mode)

        self.conn = None
        self.current_trade = None
        self._restore_done = False
        self._lock = threading.Lock()
        self._close_dedupe_ttl = 0.35
        self._last_close_mono = 0.0
        self._last_close_key = None
        self._open_fill_ctx = {}
        self._open_fill_window_sec = 2.5
        self._pending_restore_trade = None
        self._exchange_position_resolver = None
        self._suppress_next_position_close_notify = False

        self._init_db()
        self._restore_current_trade()

    def set_exchange_position_resolver(self, resolver):
        """Resolver receives symbol and returns truth: bool|dict|None."""
        self._exchange_position_resolver = resolver
        with self._lock:
            self._resolve_pending_restore()

    def _resolve_pending_restore(self):
        if self.current_trade is not None or not self._pending_restore_trade:
            return

        resolver = self._exchange_position_resolver
        if not resolver:
            return

        pending = self._pending_restore_trade
        symbol = pending.get("symbol")

        try:
            truth = resolver(symbol)
        except Exception as e:
            print("Resolve pending restore error:", e)
            return

        # Unknown truth -> keep pending, never materialize blindly.
        if truth is None:
            return

        has_pos = False
        side_ok = True

        if isinstance(truth, bool):
            has_pos = truth
        elif isinstance(truth, dict):
            size = float(truth.get("size", 0) or 0)
            has_pos = size > 0
            t_side = truth.get("side")
            p_side = pending.get("side")
            if t_side and p_side:
                side_ok = str(t_side).upper() == str(p_side).upper()
        else:
            return

        if not has_pos or not side_ok:
            self._pending_restore_trade = None
            self._clear_current_trade()
            return

        self.current_trade = pending
        self._pending_restore_trade = None
        if not self._restore_done:
            self._restore_done = True
            print(
                "♻ RESTORE OPEN TRADE:",
                self.current_trade,
                "journal_storage=",
                self.mode,
                "logical_mode=",
                self.logical_mode,
            )

    @staticmethod
    def _trade_client_order_id(data: dict):
        return data.get("client_order_id") or data.get("c")

    def _sym_key(self, symbol) -> str:
        return (symbol or "").upper()

    def _seed_open_fill_ctx(self, symbol, data: dict) -> None:
        sym = self._sym_key(symbol)
        if not sym:
            return
        coid = self._trade_client_order_id(data)
        self._open_fill_ctx[sym] = {
            "client_order_id": coid,
            "mono": time.monotonic(),
        }

    def _refresh_open_fill_ctx_mono(self, symbol, data: dict) -> None:
        sym = self._sym_key(symbol)
        if not sym:
            return
        ctx = self._open_fill_ctx.get(sym)
        if not ctx:
            self._seed_open_fill_ctx(symbol, data)
            return
        ctx["mono"] = time.monotonic()
        coid = self._trade_client_order_id(data)
        if coid and not ctx.get("client_order_id"):
            ctx["client_order_id"] = coid

    def _should_aggregate_multi_fill(self, symbol, data: dict) -> bool:
        if not self.current_trade:
            return False
        sym = self._sym_key(symbol or self.current_trade.get("symbol"))
        if not sym:
            return False
        ctx = self._open_fill_ctx.get(sym)
        if not ctx:
            return False
        age = time.monotonic() - float(ctx.get("mono", 0))
        if age >= self._open_fill_window_sec:
            return False
        dc = self._trade_client_order_id(data)
        cc = ctx.get("client_order_id")
        if cc and dc and cc != dc:
            return False
        return True

    @staticmethod
    def _opposite_leg_dust_vs_incoming_fill(
        current_size: float, incoming_size: float
    ) -> bool:
        """
        True when journal opposite leg is strictly smaller than half the new fill.

        Then Case 2's remainder (incoming - current) mis-reports the execution fill
        (e.g. SELL 0.045 → OPEN 0.024 when stale LONG ~0.021). Treat the order fill
        as authoritative: full incoming_size on the incoming side after closing dust.
        """
        if incoming_size <= 1e-18:
            return False
        return (float(current_size) * 2.0) < float(incoming_size)

    def _grow_open_position_keeping_side(
        self, new_size: float, price, fee: float, data: dict
    ) -> None:
        old_sz = float(self.current_trade["entry_size"])
        old_px = float(self.current_trade["entry_price"])
        new_sz = float(new_size)
        add = new_sz - old_sz
        if add <= 1e-12:
            return
        new_px = (old_px * old_sz + float(price) * add) / new_sz
        self.current_trade["entry_size"] = new_sz
        self.current_trade["entry_price"] = new_px
        self.current_trade["fees"] = float(self.current_trade.get("fees", 0) or 0) + float(
            fee or 0
        )
        self._persist_current_trade()
        self._refresh_open_fill_ctx_mono(self.current_trade.get("symbol"), data)

    def _is_duplicate_close(self, symbol, price, size) -> bool:
        """Exact same close payload within TTL (duplicate WS / double bus delivery)."""
        try:
            key = (
                (symbol or "").upper(),
                round(float(size), 8),
                round(float(price), 8),
            )
        except (TypeError, ValueError):
            return False
        now = time.monotonic()
        if (
            self._last_close_key == key
            and (now - self._last_close_mono) < self._close_dedupe_ttl
        ):
            return True
        self._last_close_key = key
        self._last_close_mono = now
        return False

    def handle_event(self, event_type, data):

        with self._lock:
            self._resolve_pending_restore()
            if event_type == "POSITION_OPEN":

                self.on_position_open(
                    symbol=data["symbol"],
                    side=data["side"],
                    price=data["price"],
                    size=data["size"],
                    fee=data.get("fee", 0),
                    strategy=data.get("strategy"),
                )

            elif event_type == "POSITION_CLOSE":
                if self._is_duplicate_close(
                    data.get("symbol"), data.get("price"), data.get("size")
                ):
                    return
                self._apply_close_if_open(
                    price=data["price"],
                    size=data["size"],
                    fee=data.get("fee", 0)
                )

    def handle_trade(self, data: dict):

        with self._lock:
            self._resolve_pending_restore()
            if not data:
                return

            side = data.get("side")
            price = data.get("price")
            size = data.get("size")
            fee = float(data.get("fee", 0))
            raw_et = data.get("execution_type", "OPEN") or "OPEN"
            execution_type = str(raw_et).upper()

            if not side or not price or not size:
                return

            # CLOSE before OPEN-on-None so late ORDER_TRADE_UPDATE can restore from open_trade.json
            if execution_type == "CLOSE":
                if self._is_duplicate_close(data.get("symbol"), price, size):
                    return
                self._apply_close_if_open(price, size, fee)
                return

            # nếu chưa có trade → open
            if self.current_trade is None:
                self.on_position_open(
                    symbol=data.get("symbol"),
                    side=side,
                    price=price,
                    size=size,
                    fee=fee,
                    strategy=data.get("strategy"),
                )
                self._seed_open_fill_ctx(data.get("symbol"), data)
                return

            # nếu side khác → reverse / partial reverse
            if side != self.current_trade["side"]:

                rd = self.TRADE_SIZE_ROUND_DECIMALS
                current_size = round(float(self.current_trade["entry_size"]), rd)
                incoming_size = round(float(size), rd)
                eps = self.REVERSE_FULL_CLOSE_EPS

                # Case 1 — Full close (exact or float drift, e.g. 0.02 vs 0.019999)
                if abs(incoming_size - current_size) <= eps:

                    self._apply_close_if_open(
                        price=price,
                        size=current_size,
                        fee=fee
                    )
                    return

                # Case 2 — Partial reverse
                elif incoming_size > current_size:

                    # Multi-fill same order / tight window: cumulative z, not a reverse
                    if self._should_aggregate_multi_fill(data.get("symbol"), data):
                        self._grow_open_position_keeping_side(
                            incoming_size, price, fee, data
                        )
                        return

                    # Stale tiny opposite leg: exchange fill is authoritative (full z)
                    if self._opposite_leg_dust_vs_incoming_fill(
                        current_size, incoming_size
                    ):
                        self._suppress_next_position_close_notify = True
                        self._apply_close_if_open(
                            price=price,
                            size=current_size,
                            fee=fee,
                        )
                        self.current_trade = None
                        self._clear_current_trade()
                        try:
                            from backend.notifications.trading_notifications import (
                                notify_position_reverse,
                            )

                            notify_position_reverse(
                                str(data.get("symbol") or ""),
                                str(side or ""),
                                str(self.mode),
                            )
                        except Exception:
                            pass
                        self.on_position_open(
                            symbol=data.get("symbol"),
                            side=side,
                            price=price,
                            size=incoming_size,
                            fee=fee,
                            strategy=data.get("strategy"),
                            notify=False,
                        )
                        self._seed_open_fill_ctx(data.get("symbol"), data)
                        return

                    # close current
                    self._suppress_next_position_close_notify = True
                    self._apply_close_if_open(
                        price=price,
                        size=current_size,
                        fee=fee
                    )

                    # 🔥 force clear before reverse open
                    self.current_trade = None
                    self._clear_current_trade()

                    # open remaining
                    remaining = round(incoming_size - current_size, rd)

                    try:
                        from backend.notifications.trading_notifications import (
                            notify_position_reverse,
                        )

                        notify_position_reverse(
                            str(data.get("symbol") or ""),
                            str(side or ""),
                            str(self.mode),
                        )
                    except Exception:
                        pass

                    self.on_position_open(
                        symbol=data.get("symbol"),
                        side=side,
                        price=price,
                        size=remaining,
                        fee=fee,
                        strategy=data.get("strategy"),
                        notify=False,
                    )
                    self._seed_open_fill_ctx(data.get("symbol"), data)

                    return

                # Case 3 — Partial close
                else:

                    # close partial
                    self._apply_close_if_open(
                        price=price,
                        size=incoming_size,
                        fee=fee
                    )

                    # keep remaining

                    return

            # Same-side: partial fills → cumulative position (journal was stuck on first slice)
            incoming_sz = float(size)
            current_sz = float(self.current_trade["entry_size"])
            if incoming_sz > current_sz + 1e-12 and self._should_aggregate_multi_fill(
                data.get("symbol"), data
            ):
                self._grow_open_position_keeping_side(incoming_sz, price, fee, data)

    def _apply_close_if_open(self, price, size, fee=0) -> None:
        """Close only if a position is open; ignore duplicate CLOSE (e.g. account + order path)."""
        if self.current_trade is None:
            self._restore_current_trade(force=True)
            self._resolve_pending_restore()
        if self.current_trade is None:
            return
        self.on_position_close(price, size, fee)

    def _get_open_trade_path(self):
        folder = os.path.dirname(self.db_path)
        return os.path.join(folder, "open_trade.json")


    def _persist_current_trade(self):

        try:
            if not self.current_trade:
                return

            path = self._get_open_trade_path()

            with open(path, "w") as f:
                json.dump(self.current_trade, f)
            self._pending_restore_trade = None

        except Exception as e:
            print("Persist open trade error:", e)


    def _restore_current_trade(self, force=False):

        if not force and self._restore_done:
            return

        try:
            path = self._get_open_trade_path()

            if not os.path.exists(path):
                return

            with open(path, "r") as f:
                loaded = json.load(f)

            file_mode = loaded.get("mode")
            logical = self.logical_mode
            if file_mode is not None and logical is not None and str(file_mode) != str(logical):
                print(
                    "SKIP RESTORE open_trade: trade.mode=",
                    repr(file_mode),
                    "!= journal logical_mode=",
                    repr(logical),
                    "(storage=",
                    self.mode,
                    ")",
                )
                return

            # Startup-safe: keep as pending until exchange truth confirms position exists.
            self._pending_restore_trade = loaded
            self._resolve_pending_restore()

        except Exception as e:
            print("Restore open trade error:", e)


    def _clear_current_trade(self):

        try:
            self._pending_restore_trade = None
            path = self._get_open_trade_path()

            if os.path.exists(path):
                os.remove(path)

        except Exception as e:
            print("Clear open trade error:", e)

    def _init_db(self):

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False
        )

        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (

                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,

                mode TEXT,
                symbol TEXT,
                side TEXT,

                entry_time INTEGER,
                entry_price REAL,
                entry_size REAL,

                exit_time INTEGER,
                exit_price REAL,
                exit_size REAL,

                pnl REAL,
                fees REAL,

                duration_sec INTEGER
            )
            """
        )
        cursor.execute("PRAGMA table_info(trades)")
        columns = [c[1] for c in cursor.fetchall()]

        if "strategy" not in columns:
            cursor.execute("ALTER TABLE trades ADD COLUMN strategy TEXT")

        self.conn.commit()

    def on_position_open(self, symbol, side, price, size, fee=0, strategy=None, *, notify=True):

        if price == 0:
            print("⚠ IGNORE INVALID OPEN (price=0)")
            return

        if self.current_trade is not None:
            print("⚠ DUPLICATE OPEN → IGNORE")
            return

        print("✅ OPEN SAVED:", price, size, side)

        self.current_trade = {
            "mode": self.logical_mode,
            "symbol": symbol,
            "strategy": strategy or "default",
            "side": side,
            "entry_time": int(time.time()),
            "entry_price": price,
            "entry_size": size,
            "fees": fee,
        }
        self._persist_current_trade()

        if notify:
            try:
                from backend.notifications.trading_notifications import notify_position_open

                notify_position_open(
                    str(symbol or ""),
                    str(side or ""),
                    str(self.mode),
                )
            except Exception:
                pass

    def on_position_close(self, price, size, fee=0):

        if self.current_trade is None:
            return

        sym = self._sym_key(self.current_trade.get("symbol"))

        entry_price = self.current_trade["entry_price"]
        side = self.current_trade["side"]
        current_size = float(self.current_trade["entry_size"])
        close_size = float(size or 0)

        if close_size <= 0:
            print("âš  INVALID CLOSE SIZE â†’ IGNORE")
            return

        if close_size > current_size:
            close_size = current_size

        current_fees = float(self.current_trade.get("fees", 0) or 0)
        fee_ratio = close_size / current_size if current_size > 0 else 1.0
        closed_entry_fee = current_fees * fee_ratio
        remaining_entry_fee = current_fees - closed_entry_fee

        if side == "LONG":
            pnl = round(
                (price - entry_price) *
                close_size,
                3
            )
        else:
            pnl = round(
                (entry_price - price) *
                close_size,
                3
            )

        exit_time = int(time.time())

        duration = exit_time - self.current_trade["entry_time"]

        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO trades (

                mode,
                symbol,
                strategy,
                side,

                entry_time,
                entry_price,
                entry_size,

                exit_time,
                exit_price,
                exit_size,

                pnl,
                fees,

                duration_sec

            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.mode,
                self.current_trade["symbol"],
                self.current_trade["strategy"],
                side,

                self.current_trade["entry_time"],
                entry_price,
                close_size,

                exit_time,
                price,
                close_size,

                pnl,
                closed_entry_fee + fee,

                duration
            )
        )

        self.conn.commit()

        remaining_size = current_size - close_size
        if remaining_size <= 1e-5:
            self.current_trade = None
            self._clear_current_trade()
            suppress = self._suppress_next_position_close_notify
            if suppress:
                self._suppress_next_position_close_notify = False
            else:
                try:
                    from backend.notifications.trading_notifications import (
                        notify_position_close,
                    )

                    notify_position_close(sym, str(self.mode))
                except Exception:
                    pass
        else:
            self.current_trade["entry_size"] = remaining_size
            self.current_trade["fees"] = remaining_entry_fee
            self._persist_current_trade()

        self._open_fill_ctx.pop(sym, None)

    def get_last_trades(self, limit=50):

        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM trades
            ORDER BY trade_id DESC
            LIMIT ?
            """,
            (limit,)
        )

        return cursor.fetchall()

    def close(self):

        if self.conn:
            self.conn.close()
