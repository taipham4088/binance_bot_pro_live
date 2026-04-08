import time
import requests
from backend.runtime.exchange_config import exchange_config
from backend.analytics.market_bias_engine import market_bias_engine
from backend.runtime.runtime_config import runtime_config


class DashboardCache:
    """
    Cache layer cho dashboard.

    Tổng hợp dữ liệu từ:
    - SystemStateEngine (position)
    - PnLEngine
    - MetricsEngine
    - TradeJournal
    """

    def __init__(
        self,
        pnl_engine,
        metrics_engine,
        trade_journal
    ):

        self.pnl_engine = pnl_engine
        self.metrics_engine = metrics_engine
        self.trade_journal = trade_journal

        self.cache = {}

        self.last_update = 0

        # sẽ được gắn từ FastAPI app
        self.app_state = None

    # -------------------------
    # Position
    # -------------------------

    def _get_position(self):

        try:

            manager = self.app_state.manager
            sessions = manager.sessions

            if not sessions:
                return {"side": "flat", "size": 0}

            session = list(sessions.values())[0]

            # đọc trực tiếp state realtime
            state = session.system_state.state
 
            execution = state.get("execution", {})
            positions = execution.get("positions", [])

            if not positions:
                return {"side": "flat", "size": 0}

            # 🔥 Reverse Partial Safe Net Position
            long_size = 0.0
            short_size = 0.0
            long_entry = 0.0
            short_entry = 0.0

            # 🔥 cache entry ổn định
            if not hasattr(self, "_last_entry"):
                self._last_entry = 0

            for p in positions:

                side = p.get("side", "").lower()
                size = float(p.get("size", 0))
                entry = float(p.get("entry_price", 0))

                # 🔥 tránh snapshot overwrite entry = 0
                if entry == 0 and self._last_entry != 0:
                    entry = self._last_entry
                elif entry != 0:
                    self._last_entry = entry

                if side == "long":
                    long_size += size
                    long_entry = entry

                elif side == "short":
                    short_size += size
                    short_entry = entry

            # Net position
            net = long_size - short_size

            if abs(net) < 1e-8:
                return {"side": "flat", "size": 0}

            if net > 0:
                return {
                    "symbol": p.get("symbol"),
                    "side": "long",
                    "size": abs(net),
                    "entry_price": long_entry,
                    "unrealized_pnl": 0
                }

            else:
                return {
                    "symbol": p.get("symbol"),
                    "side": "short",
                    "size": abs(net),
                    "entry_price": short_entry,
                    "unrealized_pnl": 0
                }

        except Exception:
            return {"side": "flat", "size": 0}

    # -------------------------
    # Price
    # -------------------------

    def _get_price(self, symbol):

        try:

            ticker = requests.get(
                f"{exchange_config.rest_url}/fapi/v1/ticker/24hr?symbol={symbol}",
                timeout=2
            ).json()

            return float(ticker["lastPrice"])

        except Exception as e:
            print("PRICE FETCH ERROR:", e)
            return None

    # -------------------------
    # Floating PnL (Realtime)
    # -------------------------

    def _compute_floating_pnl(self, position, price):

        try:

            if not position:
                return 0.0

            side = position.get("side", "flat")
            size = float(position.get("size", 0))
            entry = float(position.get("entry_price", 0))

            # 🔥 cache entry ổn định
            if not hasattr(self, "_last_entry"):
                self._last_entry = 0

            if entry == 0 and self._last_entry != 0:
                entry = self._last_entry
            elif entry != 0:
                self._last_entry = entry

            if side == "flat" or size == 0:
                return 0.0

            if price is None:
                return float(position.get("unrealized_pnl", 0))

            if side == "long":
                return (price - entry) * size

            if side == "short":
                return (entry - price) * size

            return 0.0

        except Exception:
            return 0.0

    # -------------------------
    # Trades (session-scoped)
    # -------------------------

    def _get_recent_trades_for_dashboard(self):
        try:
            manager = self.app_state.manager
            aid = getattr(manager, "active_session_id", None)
            if aid and aid in manager.sessions:
                j = getattr(
                    manager.sessions[aid].system_state, "trade_journal", None
                )
                if j:
                    return j.get_last_trades(200)
            for s in manager.sessions.values():
                j = getattr(s.system_state, "trade_journal", None)
                if j:
                    return j.get_last_trades(200)
        except Exception:
            pass
        if self.trade_journal:
            return self.trade_journal.get_last_trades(200)
        return []

    # -------------------------
    # Refresh
    # -------------------------

    def refresh(self):

        position = self._get_position()

        symbol = position.get("symbol", "BTCUSDT")
        price = self._get_price(symbol)

        # Floating realtime
        floating = self._compute_floating_pnl(position, price)

        self.pnl_engine.update_floating_pnl(floating)

        pnl = self.pnl_engine.summary()

        # DEBUG
        print("POSITION:", position)
        print("PRICE:", price)
        print("FLOATING:", floating)

        metrics = self.metrics_engine.summary()

        trades = self._get_recent_trades_for_dashboard()

        # ------------------------------
        # Market Bias
        # ------------------------------

        strategy_side = None

        try:
            manager = self.app_state.manager
            sessions = manager.sessions

            if sessions:
                session = list(sessions.values())[0]
                state = session.system_state.state
                strategy = state.get("strategy", {})
                strategy_side = strategy.get("side")

        except Exception:
            strategy_side = None

        market_bias_engine.update(
            position=position,
            strategy_side=strategy_side
        )

        # ------------------------------
        # Dashboard Cache
        # ------------------------------

        self.cache = {
            "timestamp": int(time.time()),
            "position": position,
            "price": price,
            "pnl": pnl,
            "metrics": metrics,
            "recent_trades": trades,
            "market_bias": market_bias_engine.get(),
            "config": runtime_config
        }

        self.last_update = time.time()

    # -------------------------
    # Get
    # -------------------------

    def get(self):

        if time.time() - self.last_update > 2:
            self.refresh()

        return self.cache