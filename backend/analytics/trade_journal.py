import sqlite3
import os
import time
import json
from backend.storage.mode_storage import mode_storage



class TradeJournal:
    _restore_done = False
    """
    TradeJournal lưu toàn bộ vòng đời trade.

    Close ingestion: POSITION_CLOSE (handle_event) and TRADE (handle_trade).
    EXECUTION is not handled here — analytics_bus sends it to ExecutionMonitor only.
    """

    def __init__(self, mode="shadow"):

        self.mode = mode
        self.db_path = mode_storage.get_trade_path(mode)

        self.conn = None
        self.current_trade = None

        self._init_db()
        self._restore_current_trade()

    def handle_event(self, event_type, data):

        if event_type == "POSITION_OPEN":

            self.on_position_open(
                symbol=data["symbol"],
                side=data["side"],
                price=data["price"],
                size=data["size"],
                fee=data.get("fee", 0)
            )

        elif event_type == "POSITION_CLOSE":

            self._apply_close_if_open(
                price=data["price"],
                size=data["size"],
                fee=data.get("fee", 0)
            )

    def handle_trade(self, data: dict):

        if not data:
            return

        side = data.get("side")
        price = data.get("price")
        size = data.get("size")
        fee = float(data.get("fee", 0))
        execution_type = data.get("execution_type", "OPEN")

        if not side or not price or not size:
            return

        # CLOSE before OPEN-on-None so late ORDER_TRADE_UPDATE can restore from open_trade.json
        if execution_type == "CLOSE":
            self._apply_close_if_open(price, size, fee)
            return

        # nếu chưa có trade → open
        if self.current_trade is None:
            self.on_position_open(
                symbol=data.get("symbol"),
                side=side,
                price=price,
                size=size,
                fee=fee
            )
            return

        # nếu side khác → reverse / partial reverse
        if side != self.current_trade["side"]:

            current_size = float(self.current_trade["entry_size"])
            incoming_size = float(size)

            # Case 1 — Full close
            if incoming_size == current_size:

                self._apply_close_if_open(
                    price=price,
                    size=current_size,
                    fee=fee
                )
                return

            # Case 2 — Partial reverse
            elif incoming_size > current_size:

                # close current
                self._apply_close_if_open(
                    price=price,
                    size=current_size,
                    fee=fee
                )

                # open remaining
                remaining = incoming_size - current_size

                self.on_position_open(
                    symbol=data.get("symbol"),
                    side=side,
                    price=price,
                    size=remaining,
                    fee=fee
                )

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

    def _apply_close_if_open(self, price, size, fee=0) -> None:
        """Close only if a position is open; ignore duplicate CLOSE (e.g. account + order path)."""
        if self.current_trade is None:
            self._restore_current_trade(force=True)
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

        except Exception as e:
            print("Persist open trade error:", e)


    def _restore_current_trade(self, force=False):

        if not force and TradeJournal._restore_done:
            return

        try:
            path = self._get_open_trade_path()

            if not os.path.exists(path):
                return

            with open(path, "r") as f:
                self.current_trade = json.load(f)

            if not TradeJournal._restore_done:
                TradeJournal._restore_done = True
                print("♻ RESTORE OPEN TRADE:", self.current_trade)

        except Exception as e:
            print("Restore open trade error:", e)


    def _clear_current_trade(self):

        try:
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

    def on_position_open(self, symbol, side, price, size, fee=0):

        if price == 0:
            print("⚠ IGNORE INVALID OPEN (price=0)")
            return

        if self.current_trade is not None:
            print("⚠ DUPLICATE OPEN → IGNORE")
            return

        print("✅ OPEN SAVED:", price, size, side)

        self.current_trade = {
            "mode": self.mode,
            "symbol": symbol,
            "strategy": "default",
            "side": side,
            "entry_time": int(time.time()),
            "entry_price": price,
            "entry_size": size,
            "fees": fee,
        }
        self._persist_current_trade()

    def on_position_close(self, price, size, fee=0):

        if self.current_trade is None:
            return

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
        else:
            self.current_trade["entry_size"] = remaining_size
            self.current_trade["fees"] = remaining_entry_fee
            self._persist_current_trade()

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
