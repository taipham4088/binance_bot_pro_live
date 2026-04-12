import os
import sqlite3

from backend.storage.mode_storage import mode_storage


class PnLEngine:
    """
    PnL Engine tính toán:

    - realized pnl
    - floating pnl
    - equity
    - drawdown
    """

    def __init__(self, db_path=None, session=None, start_balance=10000):

        if db_path is not None:
            path = db_path
        elif session is not None:
            path = mode_storage.get_session_trade_path(str(session))
        else:
            path = mode_storage.get_session_trade_path("live")

        self.db_path = path
        self.start_balance = start_balance
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)

        # floating pnl runtime
        self._floating_pnl = 0.0

    # -------------------------
    # Trade History
    # -------------------------

    def get_all_trades(self):

        cursor = self.conn.cursor()

        try:
            cursor.execute(
                """
                SELECT pnl
                FROM trades
                ORDER BY trade_id ASC
                """
            )
        except sqlite3.OperationalError:
            return []

        rows = cursor.fetchall()

        return [r[0] for r in rows]

    # -------------------------
    # Realized PnL
    # -------------------------

    def realized_pnl(self):

        trades = self.get_all_trades()

        return sum(trades)

    # -------------------------
    # Floating PnL
    # -------------------------

    def update_floating_pnl(self, floating):

        self._floating_pnl = float(floating)

    def floating_pnl(self):

        return self._floating_pnl

    # -------------------------
    # Equity
    # -------------------------

    def equity(self):

        realized = self.realized_pnl()

        return self.start_balance + realized

    def total_equity(self):

        realized = self.realized_pnl()

        return self.start_balance + realized + self._floating_pnl

    # -------------------------
    # Equity Curve (Realized Only)
    # -------------------------

    def equity_curve(self):

        trades = self.get_all_trades()

        equity = self.start_balance

        curve = []

        for pnl in trades:

            equity += pnl

            curve.append(equity)

        return curve

    # -------------------------
    # Drawdown
    # -------------------------

    def max_drawdown(self):

        curve = self.equity_curve()

        if not curve:
            return 0

        peak = curve[0]
        max_dd = 0

        for value in curve:

            if value > peak:
                peak = value

            dd = (value - peak) / peak

            if dd < max_dd:
                max_dd = dd

        return max_dd

    # -------------------------
    # Summary
    # -------------------------

    def summary(self):

        realized = self.realized_pnl()
        floating = self.floating_pnl()

        return {
            "start_balance": self.start_balance,
            "realized_pnl": realized,
            "floating_pnl": floating,
            "equity": self.equity(),
            "total_equity": self.total_equity(),
            "max_drawdown": self.max_drawdown(),
        }