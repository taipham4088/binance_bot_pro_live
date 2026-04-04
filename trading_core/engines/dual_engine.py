import pandas as pd
from trading_core.runtime.position import Position
from trading_core.analytics.equity_tracker import EquityTracker
from trading_core.engines.long_engine import LongEngine
from trading_core.engines.short_engine import ShortEngine


class DualEngine:

    def __init__(self, config, context, market, execution, account):
        self.config = config
        self.context = context

        # 🔌 ports
        self.market = market
        self.execution = execution
        self.account = account

        # analytics only
        self.equity_tracker = EquityTracker(self.account.get_balance())

        # sub engines
        self.long_engine = LongEngine()
        self.short_engine = ShortEngine()

        # internal trade state
        self.position = None
        self.trades = []

    # =========================
    # MAIN BAR HANDLER
    # =========================
    def on_bar(self, i, row, df):

        time = row["time"]
        day = time.date()

        account_state = self.account.get_state()

        # ===== reset day =====
        if account_state.current_day != day:
            self.account.reset_day(day)

        # ===== daily block =====
        if account_state.blocked_until and time < account_state.blocked_until:
            return

        if account_state.daily_loss_count >= self.config.daily_stop_losses:
            return

        if self.account.daily_dd() >= self.config.daily_dd_limit:
            self.account.block_until(time + pd.Timedelta(hours=24))
            return

        # ===== manage open position =====
        if self.position:
            self._manage_position(row)
            self.equity_tracker.update(time, self.account.get_equity())
            return

        # ===== engine signals =====
        long_signal = None
        short_signal = None
        equity = self.account.get_equity()

        if self.config.trade_mode in ("long", "dual"):
            if row["valid_long"] and row["close_1h"] > row["ema200"]:
                long_signal = self.long_engine.on_bar(
                    i, row, df, self.context, equity
                )

        if self.config.trade_mode in ("short", "dual"):
            if row["valid_short"] and row["close_1h"] < row["ema200"]:
                short_signal = self.short_engine.on_bar(
                    i, row, df, self.context, equity
                )

        # ===== conflict rule =====
        if long_signal and not short_signal:
            long_signal["side"] = "LONG"
            self._open_position(long_signal)

        elif short_signal and not long_signal:
            short_signal["side"] = "SHORT"
            self._open_position(short_signal)

        elif long_signal and short_signal:
            if long_signal["breakout_time"] <= short_signal["breakout_time"]:
                long_signal["side"] = "LONG"
                self._open_position(long_signal)
            else:
                short_signal["side"] = "SHORT"
                self._open_position(short_signal)

    # =========================
    # OPEN POSITION
    # =========================
    def _open_position(self, signal):

        self.position = Position(signal)

        order_intent = {
            "side": signal["side"],
            "entry": signal["entry"],
            "sl": signal["sl"],
            "tp": signal["tp"],
            "risk": signal["risk"],
            "meta": signal
        }

        # 🚀 gửi lệnh qua execution port
        self.execution.send_order(order_intent)

    # =========================
    # MANAGE POSITION
    # =========================
    def _manage_position(self, row):

        pos = self.position
        p = pos.as_dict()

        if pos.side == "LONG":

            if row["low"] <= p["sl"]:
                self.account.register_loss(p["risk"])
                self._close_trade(row, p["sl"], -p["risk"])

            elif row["high"] >= p["tp"]:
                win = p["risk"] * self.context.rr
                self.account.register_win(win)
                self._close_trade(row, p["tp"], win)

        elif pos.side == "SHORT":

            if row["high"] >= p["sl"]:
                self.account.register_loss(p["risk"])
                self._close_trade(row, p["sl"], -p["risk"])

            elif row["low"] <= p["tp"]:
                win = p["risk"] * self.context.rr
                self.account.register_win(win)
                self._close_trade(row, p["tp"], win)

    # =========================
    # CLOSE TRADE
    # =========================
    def _close_trade(self, row, exit_price, result):

        p = self.position.as_dict()

        trade = {
            **p,
            "exit_time": row["time"],
            "exit_price": exit_price,
            "result": result,
            "balance": self.account.get_equity()
        }

        self.trades.append(trade)
        self.position = None
