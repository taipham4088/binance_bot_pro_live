import pandas as pd
from trading_core.runtime.position import Position
from trading_core.analytics.equity_tracker import EquityTracker
from trading_core.engines.long_engine import LongEngine
from trading_core.engines.short_engine import ShortEngine


class _DefaultBacktestExecutionAdapter:
    """In-process sink when no execution_adapter is supplied (e.g. CSV backtest)."""

    def send_order(self, order_intent: dict):
        return None


class _DefaultBacktestAccount:
    """Minimal account when none is supplied (keeps trading_core runners self-contained)."""

    def __init__(self, balance: float = 10000.0):
        self.balance = balance
        self._blocked_until = None
        self._current_day = None
        self.daily_loss_count = 0

    def get_balance(self):
        return self.balance

    def get_equity(self):
        return self.balance

    def get_state(self):
        class State:
            pass

        s = State()
        s.current_day = self._current_day
        s.blocked_until = self._blocked_until
        s.daily_loss_count = self.daily_loss_count
        return s

    def register_loss(self, v):
        self.balance -= v

    def register_win(self, v):
        self.balance += v

    def reset_day(self, day):
        self._current_day = day

    def daily_dd(self):
        return 0

    def block_until(self, until):
        self._blocked_until = until


class DualEngine:

    def __init__(self, config, context, market=None, execution_adapter=None, account=None):
        self.config = config
        self.context = context
        self.long_enabled = getattr(self.config, "trade_mode", "dual") in ("long", "dual")
        self.short_enabled = getattr(self.config, "trade_mode", "dual") in ("short", "dual")
        print("[DUAL ENGINE INIT]")
        print("trade_mode =", getattr(config, "trade_mode", None))
        print("[DUAL ENGINE CONFIG]")
        print("trade_mode =", getattr(config, "trade_mode", None))
        print("risk =", getattr(config, "risk_per_trade", None))
        print("balance =", getattr(config, "initial_balance", None))

        # 🔌 ports
        self.market = market
        if execution_adapter is None:
            execution_adapter = _DefaultBacktestExecutionAdapter()
        self.execution_adapter = execution_adapter
        if account is None:
            account = _DefaultBacktestAccount()
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
        self.long_enabled = getattr(self.config, "trade_mode", "dual") in ("long", "dual")
        self.short_enabled = getattr(self.config, "trade_mode", "dual") in ("short", "dual")
        print("[ENGINE MODE]")
        print("long_enabled =", self.long_enabled)
        print("short_enabled =", self.short_enabled)

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

        entry = signal.get("entry") or signal.get("entry_price")

        if entry is None:
            return

        self.position = Position(signal)

        order_intent = {
            "side": signal["side"],
            "entry": entry,
            "sl": signal["sl"],
            "tp": signal["tp"],
            "risk": signal["risk"],
            "meta": signal
        }

        # 🚀 execution pipeline (live: StrategyExecutionAdapter → inject_intent)
        self.execution_adapter.send_order(order_intent)

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
