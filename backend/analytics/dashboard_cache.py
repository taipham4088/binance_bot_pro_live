import time
import requests
from backend.runtime.exchange_config import exchange_config
from backend.utils.symbol_utils import extract_quote_asset
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
        self._float_entry_by_session: dict[str, float] = {}

    # -------------------------
    # Session helpers
    # -------------------------

    @staticmethod
    def _pick_primary_session(manager):
        aid = getattr(manager, "active_session_id", None)
        if aid and aid in manager.sessions:
            return manager.sessions[aid]
        for sid in ("live", "shadow"):
            if sid in manager.sessions:
                return manager.sessions[sid]
        if manager.sessions:
            return next(iter(manager.sessions.values()))
        return None

    @staticmethod
    def _display_mode(session) -> str:
        api = str(getattr(session, "api_mode", "") or "").strip().upper()
        return api if api else "UNKNOWN"

    @staticmethod
    def _session_sort_key(item):
        sid, _sess = item
        order = {"live": 0, "shadow": 1}
        return (order.get(sid, 50), sid)

    # -------------------------
    # Position
    # -------------------------

    def _get_position_for_session(self, session):

        try:
            state = session.system_state.state
            execution = state.get("execution", {})
            positions = execution.get("positions", [])

            if not positions:
                return {"side": "flat", "size": 0}

            long_size = 0.0
            short_size = 0.0
            long_entry = 0.0
            short_entry = 0.0

            sid = str(getattr(session, "id", ""))
            prev = self._float_entry_by_session.get(sid, 0.0)

            for p in positions:
                side = p.get("side", "").lower()
                size = float(p.get("size", 0))
                entry = float(p.get("entry_price", 0))

                if entry == 0 and prev != 0:
                    entry = prev
                elif entry != 0:
                    self._float_entry_by_session[sid] = entry
                    prev = entry

                if side == "long":
                    long_size += size
                    long_entry = entry
                elif side == "short":
                    short_size += size
                    short_entry = entry

            net = long_size - short_size

            if abs(net) < 1e-8:
                return {"side": "flat", "size": 0}

            if net > 0:
                return {
                    "symbol": p.get("symbol"),
                    "side": "long",
                    "size": abs(net),
                    "entry_price": long_entry,
                    "unrealized_pnl": 0,
                }

            return {
                "symbol": p.get("symbol"),
                "side": "short",
                "size": abs(net),
                "entry_price": short_entry,
                "unrealized_pnl": 0,
            }

        except Exception:
            return {"side": "flat", "size": 0}

    def _get_position(self):

        try:
            manager = self.app_state.manager
            sessions = manager.sessions
            if not sessions:
                return {"side": "flat", "size": 0}
            session = self._pick_primary_session(manager)
            if not session:
                return {"side": "flat", "size": 0}
            return self._get_position_for_session(session)
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

        manager = getattr(self.app_state, "manager", None) if self.app_state else None
        primary = self._pick_primary_session(manager) if manager else None

        position = (
            self._get_position_for_session(primary)
            if primary
            else {"side": "flat", "size": 0}
        )

        if primary:
            symbol = (
                position.get("symbol")
                or getattr(primary, "active_symbol", None)
                or primary._initial_symbol_from_config()
            )
        else:
            symbol = runtime_config.get("symbol", "BTCUSDT")

        price = self._get_price(symbol)
        floating_primary = self._compute_floating_pnl(position, price)

        self.pnl_engine.update_floating_pnl(floating_primary)

        pnl = self.pnl_engine.summary()

        panels = []

        if not manager or not manager.sessions:
            panels.append(
                {
                    "session_id": None,
                    "mode": "NONE",
                    "symbol": None,
                    "quote_asset": None,
                    "equity": None,
                    "floating": None,
                    "total_equity": None,
                    "exchange_wallet_quote": None,
                    "exchange_wallet_usdt": None,
                    "account_equity": None,
                }
            )
            pnl["panels"] = panels
            pnl["session_status"] = "no_session"
            pnl["session_label"] = "No Active Session"
            pnl["mode"] = None
            pnl["symbol"] = None
            pnl["quote_asset"] = None
            pnl["trading_quote_asset"] = None
            pnl["equity"] = None
            pnl["total_equity"] = None
            pnl["floating_pnl"] = None
            pnl["exchange_wallet_quote"] = None
            pnl["exchange_wallet_usdt"] = None
            pnl["account_equity"] = None
        else:
            for _sid, session in sorted(
                manager.sessions.items(), key=DashboardCache._session_sort_key
            ):
                pos = self._get_position_for_session(session)
                sym = (
                    pos.get("symbol")
                    or getattr(session, "active_symbol", None)
                    or session._initial_symbol_from_config()
                )
                px = self._get_price(sym)
                fl = self._compute_floating_pnl(pos, px)
                quote = extract_quote_asset(sym)
                mode_disp = self._display_mode(session)
                panel = {
                    "session_id": session.id,
                    "mode": mode_disp,
                    "symbol": sym,
                    "quote_asset": quote,
                    "equity": None,
                    "floating": fl,
                    "total_equity": None,
                    "exchange_wallet_quote": None,
                    "exchange_wallet_usdt": None,
                    "account_equity": None,
                }
                try:
                    eng = getattr(session, "engine", None)
                    if eng is not None and getattr(eng, "sync_engine", None):
                        acct = eng.sync_engine.account
                        wallet = float(session.get_dynamic_equity())
                        panel["exchange_wallet_quote"] = wallet
                        panel["exchange_wallet_usdt"] = float(acct.get_equity("USDT"))
                        panel["equity"] = wallet
                        panel["total_equity"] = wallet + fl
                        btc_px = self._get_price("BTCUSDT")
                        eth_px = self._get_price("ETHUSDT")
                        panel["account_equity"] = acct.total_account_equity_usdt(
                            btc_usdt=btc_px,
                            eth_usdt=eth_px,
                        )
                    else:
                        w = float(session.get_dynamic_equity())
                        panel["equity"] = w
                        panel["total_equity"] = w + fl
                        panel["exchange_wallet_quote"] = w
                except Exception:
                    pass
                panels.append(panel)

            pnl["panels"] = panels
            pnl["session_status"] = "multi" if len(panels) > 1 else "single"
            pnl["session_label"] = None

            if len(panels) == 1:
                p0 = panels[0]
                pnl["mode"] = p0["mode"]
                pnl["symbol"] = p0["symbol"]
                pnl["quote_asset"] = p0["quote_asset"]
                pnl["trading_quote_asset"] = p0["quote_asset"]
                pnl["floating_pnl"] = p0["floating"]
                pnl["equity"] = p0["equity"]
                pnl["total_equity"] = p0["total_equity"]
                pnl["exchange_wallet_quote"] = p0["exchange_wallet_quote"]
                pnl["exchange_wallet_usdt"] = p0["exchange_wallet_usdt"]
                pnl["account_equity"] = p0["account_equity"]
            else:
                pnl["mode"] = "MULTI"
                pnl["symbol"] = None
                pnl["quote_asset"] = None
                pnl["trading_quote_asset"] = None
                pnl["floating_pnl"] = None
                pnl["equity"] = None
                pnl["total_equity"] = None
                pnl["exchange_wallet_quote"] = None
                pnl["exchange_wallet_usdt"] = None
                pnl["account_equity"] = None

        # DEBUG
        print("POSITION:", position)
        print("PRICE:", price)
        print("FLOATING:", floating_primary)

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