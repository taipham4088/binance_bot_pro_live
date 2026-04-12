import time
import requests
from copy import deepcopy
from backend.runtime.exchange_config import exchange_config
from backend.utils.symbol_utils import extract_quote_asset
from backend.analytics.market_bias_engine import market_bias_engine
from backend.runtime.runtime_config import runtime_config
from backend.storage.mode_storage import mode_storage
from backend.analytics.metrics_engine import MetricsEngine

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
        self._metrics_engine_by_session: dict[str, MetricsEngine] = {}

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

    def _merge_risk_views(self, session):
        merged = {}
        if session is None:
            return merged
        try:
            if getattr(session, "risk_system", None):
                merged.update(session.risk_system.snapshot() or {})
        except Exception:
            pass
        try:
            st = session.system_state.state.get("risk") or {}
            for k, v in st.items():
                if v is not None:
                    merged[k] = v
        except Exception:
            pass
        return merged

    def _build_risk_status(self, primary, pnl_summary: dict | None) -> dict:
        """
        Observability-only aggregate of risk gates (session + optional risk_engine snap).
        """
        pnl_summary = pnl_summary or {}
        now = int(time.time())

        def _blank_rules():
            return {
                "consecutive_loss": {
                    "loss_streak": None,
                    "limit": None,
                    "status": "OK",
                },
                "daily_loss_limit": {
                    "daily_loss": None,
                    "max_daily_loss": None,
                    "status": "OK",
                },
                "cooldown": {
                    "cooldown_active": False,
                    "remaining_time": None,
                    "status": "INACTIVE",
                },
                "max_drawdown": {
                    "drawdown": None,
                    "max_drawdown": None,
                    "status": "OK",
                    "daily_start_equity": None,
                    "current_equity": None,
                    "daily_drawdown_pct": None,
                    "daily_limit_pct": None,
                    "active": False,
                },
            }

        if primary is None:
            return {
                "trade_allowed": False,
                "blocked_rules": [],
                "rules": _blank_rules(),
                "session_id": None,
                "daily_equity_risk": {},
            }

        rc = {}
        try:
            rc = primary.get_risk_config() or {}
        except Exception:
            rc = {}

        max_streak_cfg = int(rc.get("daily_stop_losses", 2))
        max_daily_frac = float(rc.get("daily_dd_limit", 0.05))

        rs_view = self._merge_risk_views(primary)
        ro_state = str(rs_view.get("state") or "").upper()

        cu_raw = rs_view.get("cooldown_until")
        cu_int = None
        if cu_raw is not None:
            try:
                cu_int = int(cu_raw)
            except (TypeError, ValueError):
                cu_int = None

        cooldown_active = bool(cu_int is not None and cu_int > now)
        remaining = (cu_int - now) if cooldown_active else None

        re_snap = None
        re = getattr(primary, "risk_engine", None)
        if re is not None and callable(getattr(re, "snapshot", None)):
            try:
                re_snap = re.snapshot()
            except Exception:
                re_snap = None

        loss_streak = 0
        entry_blocked = False

        den: dict = {}
        try:
            if hasattr(primary, "get_daily_equity_risk_snapshot"):
                den = primary.get_daily_equity_risk_snapshot() or {}
        except Exception:
            den = {}

        daily_active = bool(den.get("daily_started"))
        daily_dd_blocked = bool(den.get("blocked")) if daily_active else False
        dd_pct_display = den.get("daily_drawdown_pct")
        limit_pct_display = den.get("daily_limit_pct")
        lim_neg_pct = (
            -abs(float(limit_pct_display))
            if daily_active and limit_pct_display is not None
            else None
        )

        if re_snap and isinstance(re_snap.get("daily"), dict):
            daily = re_snap["daily"]
            loss_streak = int(daily.get("consecutive_losses", 0))
            entry_blocked = bool(daily.get("entry_blocked", False))
        else:
            sa = getattr(primary, "strategy_account", None)
            if sa is not None and callable(getattr(sa, "get_state", None)):
                st = sa.get_state()
                loss_streak = int(getattr(st, "daily_loss_count", 0) or 0)

        daily_loss_frac = 0.0
        sa = getattr(primary, "strategy_account", None)
        if sa is not None and callable(getattr(sa, "daily_dd", None)):
            try:
                daily_loss_frac = float(sa.daily_dd())
            except Exception:
                daily_loss_frac = 0.0

        backend_kill = bool(
            re_snap and ("kill_switch" in re_snap) and re_snap.get("kill_switch")
        )

        blocked: list[str] = []

        cl_blocked = entry_blocked or (
            max_streak_cfg > 0 and loss_streak >= max_streak_cfg
        )
        if cl_blocked:
            blocked.append("consecutive_loss")

        dl_blocked = backend_kill or (
            max_daily_frac > 0 and daily_loss_frac >= max_daily_frac
        )
        if dl_blocked:
            blocked.append("daily_loss_limit")

        if cooldown_active:
            blocked.append("cooldown")

        if daily_dd_blocked:
            blocked.append("daily_equity_drawdown")

        if ro_state == "BLOCKED":
            blocked.append("manual_block")
        if ro_state == "FROZEN":
            blocked.append("manual_freeze")

        rules = {
            "consecutive_loss": {
                "loss_streak": loss_streak,
                "limit": max_streak_cfg,
                "status": "BLOCKED" if cl_blocked else "OK",
            },
            "daily_loss_limit": {
                "daily_loss": daily_loss_frac,
                "max_daily_loss": max_daily_frac,
                "status": "BLOCKED" if dl_blocked else "OK",
            },
            "cooldown": {
                "cooldown_active": cooldown_active,
                "remaining_time": remaining,
                "status": "ACTIVE" if cooldown_active else "INACTIVE",
            },
            "max_drawdown": {
                "daily_start_equity": den.get("daily_start_equity"),
                "current_equity": den.get("current_equity"),
                "daily_drawdown_pct": dd_pct_display,
                "daily_limit_pct": limit_pct_display,
                "utc_date": den.get("utc_date"),
                "active": daily_active,
                "drawdown": dd_pct_display,
                "max_drawdown": lim_neg_pct,
                "status": "BLOCKED" if daily_dd_blocked else "OK",
            },
        }

        return {
            "trade_allowed": len(blocked) == 0,
            "blocked_rules": blocked,
            "rules": rules,
            "session_id": getattr(primary, "id", None),
            "readonly_state": ro_state or None,
            "daily_equity_risk": den,
        }

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

    @staticmethod
    def _normalize_session_id(session_id: str | None) -> str:
        if not session_id:
            return "live"
        return str(session_id).strip().lower()

    def invalidate_session_analytics(self, session_id: str | None) -> None:
        """Drop cached MetricsEngine after archive/reset so the next read reopens the DB."""
        sid = self._normalize_session_id(session_id)
        self._metrics_engine_by_session.pop(sid, None)

    def _metrics_summary_for_session_db(self, session_id: str) -> dict:
        sid = self._normalize_session_id(session_id)
        path = mode_storage.get_session_trade_path(sid)
        eng = self._metrics_engine_by_session.get(sid)
        if eng is None or getattr(eng, "db_path", None) != path:
            eng = MetricsEngine(db_path=path)
            self._metrics_engine_by_session[sid] = eng
        return eng.summary()

    @staticmethod
    def _mode_matches_session(mode: str | None, session_id: str) -> bool:
        if not mode:
            return False
        mode_norm = str(mode).strip().lower()
        if session_id == "live":
            return mode_norm == "live"
        if session_id == "shadow":
            return mode_norm == "shadow"
        if session_id == "paper":
            return mode_norm == "paper"
        if session_id == "backtest":
            return mode_norm == "backtest"
        return False

    @staticmethod
    def _blank_position() -> dict:
        return {"side": "flat", "size": 0}

    @staticmethod
    def _blank_risk_status(session_id: str | None) -> dict:
        return {
            "trade_allowed": False,
            "blocked_rules": [],
            "rules": {},
            "session_id": session_id,
            "daily_equity_risk": {},
        }

    def _filter_payload_by_session(
        self,
        payload: dict,
        session_id: str | None,
        dual_panel: bool,
    ) -> dict:
        out = deepcopy(payload)
        pnl = out.get("pnl") or {}
        panels = list(pnl.get("panels") or [])
        target = self._normalize_session_id(session_id)

        if dual_panel:
            selected_panels = [
                p for p in panels
                if str(p.get("session_id", "")).lower() in ("live", "shadow")
            ]
            pnl["panels"] = selected_panels
            pnl["session_status"] = "multi" if len(selected_panels) > 1 else "single"
            pnl["session_label"] = "LIVE | SHADOW" if len(selected_panels) > 1 else None
            pnl["mode"] = "MULTI" if len(selected_panels) > 1 else (selected_panels[0].get("mode") if selected_panels else None)
            out["position"] = self._blank_position()
            out["risk_status"] = self._blank_risk_status("live_shadow")
            out["metrics"] = self._metrics_summary_for_session_db("live")
            return out

        panel = None
        for p in panels:
            if str(p.get("session_id", "")).lower() == target:
                panel = p
                break

        manager = getattr(self.app_state, "manager", None) if self.app_state else None
        session = None
        if manager is not None:
            session = (getattr(manager, "sessions", {}) or {}).get(target)

        if panel is not None:
            pnl["panels"] = [panel]
            pnl["session_status"] = "single"
            pnl["session_label"] = None
            pnl["mode"] = panel.get("mode")
            pnl["symbol"] = panel.get("symbol")
            pnl["quote_asset"] = panel.get("quote_asset")
            pnl["trading_quote_asset"] = panel.get("quote_asset")
            pnl["floating_pnl"] = panel.get("floating")
            pnl["equity"] = panel.get("equity")
            pnl["total_equity"] = panel.get("total_equity")
            pnl["exchange_wallet_quote"] = panel.get("exchange_wallet_quote")
            pnl["exchange_wallet_usdt"] = panel.get("exchange_wallet_usdt")
            pnl["account_equity"] = panel.get("account_equity")
        else:
            pnl["panels"] = []
            pnl["session_status"] = "no_session"
            pnl["session_label"] = f"No Active Session ({target.upper()})"
            pnl["mode"] = target.upper()
            pnl["symbol"] = None
            pnl["quote_asset"] = None
            pnl["trading_quote_asset"] = None
            pnl["floating_pnl"] = None
            pnl["equity"] = None
            pnl["total_equity"] = None
            pnl["exchange_wallet_quote"] = None
            pnl["exchange_wallet_usdt"] = None
            pnl["account_equity"] = None

        if session is not None:
            out["position"] = self._get_position_for_session(session)
            out["risk_status"] = self._build_risk_status(session, pnl)
            session_trades = []
            try:
                j = getattr(session.system_state, "trade_journal", None)
                if j:
                    session_trades = j.get_last_trades(200)
            except Exception:
                session_trades = []
            out["recent_trades"] = session_trades
        else:
            out["position"] = self._blank_position()
            out["risk_status"] = self._blank_risk_status(target)
            out["recent_trades"] = [
                t for t in list(out.get("recent_trades") or [])
                if isinstance(t, dict) and self._mode_matches_session(t.get("mode"), target)
            ]

        if session is not None and getattr(session, "mode", None) == "backtest":
            try:
                snap = session.state_bus.snapshot()
                if isinstance(snap, dict):
                    if snap.get("backtest_progress") is not None:
                        pnl["backtest_progress"] = snap["backtest_progress"]
                    if snap.get("trade_count") is not None:
                        pnl["trade_count"] = snap["trade_count"]
                acc = getattr(session, "account", None)
                if acc is not None:
                    eq = float(acc.get_equity())
                    pnl["equity"] = eq
                    fl = float(pnl.get("floating_pnl") or 0)
                    pnl["total_equity"] = eq + fl
                    if pnl.get("panels") and len(pnl["panels"]) == 1:
                        p0 = pnl["panels"][0]
                        p0["equity"] = eq
                        p0["total_equity"] = pnl["total_equity"]
            except Exception:
                pass

        out["metrics"] = self._metrics_summary_for_session_db(target)
        return out

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
                    if getattr(session, "mode", None) == "backtest":
                        acc = getattr(session, "account", None)
                        if acc is not None:
                            eq = float(acc.get_equity())
                            panel["equity"] = eq
                            panel["total_equity"] = eq + fl
                            panel["exchange_wallet_quote"] = eq
                        snap = getattr(session.state_bus, "snapshot", lambda: {})()
                        if isinstance(snap, dict):
                            if snap.get("backtest_progress") is not None:
                                panel["backtest_progress"] = snap["backtest_progress"]
                            if snap.get("trade_count") is not None:
                                panel["trade_count"] = snap["trade_count"]
                    else:
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
                if p0.get("backtest_progress") is not None:
                    pnl["backtest_progress"] = p0["backtest_progress"]
                if p0.get("trade_count") is not None:
                    pnl["trade_count"] = p0["trade_count"]
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

        risk_status = self._build_risk_status(primary, pnl)

        # ------------------------------
        # Dashboard Cache
        # ------------------------------

        self.cache = {
            "timestamp": int(time.time()),
            "position": position,
            "price": price,
            "pnl": pnl,
            "risk_status": risk_status,
            "metrics": metrics,
            "recent_trades": trades,
            "market_bias": market_bias_engine.get(),
            "config": runtime_config
        }

        self.last_update = time.time()

    # -------------------------
    # Get
    # -------------------------

    def get(self, session_id: str | None = None, dual_panel: bool = False):

        if time.time() - self.last_update > 2:
            self.refresh()

        if session_id or dual_panel:
            return self._filter_payload_by_session(self.cache, session_id, dual_panel)
        return self.cache