import asyncio
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from backend.utils.symbol_utils import extract_quote_asset
from backend.strategy.strategy_router import StrategyRouter
from backend.core.system_state_engine import SystemStateEngine
from backend.risk.readonly_risk_system import ReadOnlyRiskSystem
from backend.reconciliation.reconciliation_hub import ReconciliationHub
from trading_core.analytics.streaming.system_state_bus import SystemStateBus
from execution.orchestrator.orchestrator import ExecutionOrchestrator

print("🔥 SESSION FILE:", __file__)


def canonical_session_id(mode: str) -> str:
    """Stable API id for /session/start/{id} and WS paths."""
    m = str(mode or "").strip().lower().replace("-", "_")
    if m == "live":
        return "live"
    if m == "shadow":
        return "shadow"
    if m == "live_shadow":
        return "live_shadow"
    if m == "backtest":
        return "backtest"
    if m == "paper":
        return "paper"
    return "paper"


def mode_defers_execution_bootstrap(mode: str) -> bool:
    """Shadow / live modes: build execution stack on start(), not on create."""
    m = str(mode or "").strip().lower().replace("-", "_")
    return m in ("shadow", "live", "live_shadow")


@dataclass
class SymbolContext:
    """
    Per-symbol market + future strategy/position slices (multi-symbol ready).
    Single active symbol uses one live market at a time.
    """

    symbol: str
    market: Any = None


class TradingSession:
    """
    App Host Kernel

    A running trading system instance.
    """

    STATUS_CREATED = "CREATED"
    STATUS_READY = "READY"
    STATUS_RUNNING = "RUNNING"
    STATUS_FROZEN = "FROZEN"
    STATUS_STOPPED = "STOPPED"
    STATUS_ERROR = "ERROR"

    def __init__(
        self,
        mode,
        config,
        app=None,
        session_id: str | None = None,
        defer_execution: bool | None = None,
    ):
        # ---- identity (api_mode = control-plane name; mode = execution factory name) ----
        raw = str(mode or "").strip().lower().replace("-", "_")
        self.api_mode = raw
        self.mode = raw
        if raw == "live_shadow":
            self.mode = "shadow"
        self.config = config or {}
        # ---- runtime risk config ----
        if isinstance(self.config, dict):

            self.risk_config = {
                "risk_per_trade": self.config.get("risk_per_trade", 0.01),
                "daily_dd_limit": self.config.get("daily_dd_limit", 0.05),
                "daily_stop_losses": self.config.get("daily_stop_losses", 3),
                "max_positions": self.config.get("max_positions", 1)
            }

        else:

            self.risk_config = {
                "risk_per_trade": getattr(self.config, "risk_per_trade", 0.01),
                "daily_dd_limit": getattr(self.config, "daily_dd_limit", 0.05),
                "daily_stop_losses": getattr(self.config, "daily_stop_losses", 3),
                "max_positions": getattr(self.config, "max_positions", 1)
            }
        # ---- max positions (PHASE 5.5) ----
        if isinstance(self.config, dict):
            self.max_positions = self.config.get("max_positions", 1)
        else:
            self.max_positions = getattr(self.config, "max_positions", 1)

        # ---- symbol routing (single active; pending when position open) ----
        self.symbol_contexts: Dict[str, SymbolContext] = {}
        self.pending_symbol: Optional[str] = None
        self.active_symbol: str = self._initial_symbol_from_config()
        self._symbol_switch_lock = threading.Lock()

        if session_id is not None:
            self.id = str(session_id)
        elif isinstance(self.config, dict) and self.config.get("id"):
            self.id = str(self.config["id"])
        else:
            self.id = canonical_session_id(mode)

        self.app = app
        self.created_at = datetime.utcnow()
        self.status = self.STATUS_CREATED

        # ---- system state engine (WS output lives here) ----
        self.system_state = SystemStateEngine(
            session=self,
            state_hub=self.app.state.state_hub
        )

        # ---- state & events ----
        self.state_bus = SystemStateBus()
        self.last_error = None

        # ---- strategy router ----
        self.strategy_router = StrategyRouter()
        
        # ---- system core ----
        self._execution_attached = False
        if defer_execution is None:
            defer_execution = mode_defers_execution_bootstrap(mode)
        self._defer_execution_build = defer_execution

        if not self._defer_execution_build:
            self._attach_execution_stack()
        else:
            self.executor = None
            self.live_system = None
            self.engine = None
            self.strategy_engine = None
            self.execution_window = None
            self.execution_journal = None
            self.execution_orchestrator = None
            self.data_feed = None
            self.runner = None

        self.risk_system = ReadOnlyRiskSystem(
            session_id=self.id,
            mode=self.mode
        )

        # ---- daily equity drawdown (UTC day, baseline = equity at first OPENED/CLOSED) ----
        self._daily_equity_utc_date: str | None = None
        self._daily_equity_started: bool = False
        self._daily_start_equity: float | None = None
        self._daily_equity_dd_blocked: bool = False

        self._restart_guard = None
        self._supervisor = None
        self._drift_detector = None
        self._invariants = None
        # ---- reconciliation hub (PHASE 4.4.2) ----
        self.reconciliation_hub = ReconciliationHub(
            session_id=self.id,
            mode=self.mode,
            state_hub=self.app.state.state_hub
        )
        
        # ---- idempotency guard (PHASE 5.3) ----
        self.processed_intents = set()
        
        # ---- execution lock (race condition guard) ----
        self.execution_lock = asyncio.Lock()
        
        print(
            "[SESSION][INIT]",
            "id=", self.id,
            "mode=", self.mode,
            "execution_deferred=", self._defer_execution_build,
            "has_recon=", hasattr(self, "reconciliation_hub"),
        )

    def _initial_symbol_from_config(self) -> str:
        if isinstance(self.config, dict):
            s = self.config.get("symbol") or "BTCUSDT"
        else:
            s = getattr(self.config, "symbol", None) or "BTCUSDT"
        s = str(s).strip().upper()
        return s or "BTCUSDT"

    @staticmethod
    def _normalize_symbol(raw) -> Optional[str]:
        if raw is None:
            return None
        s = str(raw).strip().upper()
        return s if s else None

    def _write_config_symbol(self, symbol: str) -> None:
        if isinstance(self.config, dict):
            self.config["symbol"] = symbol
        elif hasattr(self.config, "symbol"):
            setattr(self.config, "symbol", symbol)

    def _has_open_position(self) -> bool:
        se = getattr(self, "strategy_engine", None)
        if se is not None and getattr(se, "position", None) is not None:
            return True
        eng = getattr(self, "engine", None)
        sync = getattr(eng, "sync_engine", None) if eng else None
        if sync is not None and hasattr(sync, "position"):
            try:
                for p in sync.position.get_all():
                    sz = float(getattr(p, "size", 0) or 0)
                    if abs(sz) > 1e-8:
                        return True
            except Exception:
                pass
        return False

    def request_symbol_change(self, new_symbol: str) -> dict:
        sym = self._normalize_symbol(new_symbol)
        if not sym:
            return {"status": "error", "reason": "invalid_symbol"}
        if sym == self.active_symbol:
            self.pending_symbol = None
            return {"status": "noop", "active": sym}
        if self._has_open_position():
            self.pending_symbol = sym
            return {
                "status": "pending",
                "pending": sym,
                "active": self.active_symbol,
            }
        self._apply_symbol_switch(sym)
        self.pending_symbol = None
        return {"status": "applied", "active": self.active_symbol}

    def _apply_symbol_switch(self, new_symbol: str) -> None:
        self._write_config_symbol(new_symbol)
        self.active_symbol = new_symbol

        old_market = getattr(self, "market", None)
        if old_market is not None and type(old_market).__name__ == "BinanceMarketAdapter":
            from backend.adapters.market.binance_market_adapter import BinanceMarketAdapter
            from backend.runtime.live_runner import LiveRunner

            runner = getattr(self, "runner", None)
            if runner is not None and runner.is_alive():
                runner.stop()
                runner.join(timeout=10.0)

            if hasattr(old_market, "stop"):
                old_market.stop()

            entry_iv = getattr(old_market, "entry_interval", None) or getattr(
                old_market, "tf", "5m"
            )
            reg_iv = getattr(old_market, "regime_interval", "1h")
            new_market = BinanceMarketAdapter(
                new_symbol,
                entry_iv,
                reg_iv,
                session_id=getattr(self, "id", None),
            )
            self.symbol_contexts[new_symbol] = SymbolContext(
                symbol=new_symbol, market=new_market
            )

            self.market = new_market
            self.data_feed = new_market

            se = getattr(self, "strategy_engine", None)
            if se is not None:
                se.market = new_market
                from trading_core.engines.long_engine import LongEngine
                from trading_core.engines.short_engine import ShortEngine

                se.long_engine = LongEngine()
                se.short_engine = ShortEngine()
                se.position = None

            new_runner = LiveRunner(self, new_market)
            self.runner = new_runner
            new_runner.start()
            return

        se = getattr(self, "strategy_engine", None)
        if se is not None:
            from trading_core.engines.long_engine import LongEngine
            from trading_core.engines.short_engine import ShortEngine

            se.long_engine = LongEngine()
            se.short_engine = ShortEngine()
            se.position = None

    def try_apply_pending_symbol(self) -> bool:
        runner = getattr(self, "runner", None)
        if runner is not None and threading.current_thread() is runner:

            def _bg():
                try:
                    self._try_apply_pending_symbol_impl()
                except Exception as e:
                    print("[SESSION] pending symbol apply failed:", e)

            threading.Thread(target=_bg, daemon=True).start()
            return True
        return self._try_apply_pending_symbol_impl()

    def _try_apply_pending_symbol_impl(self) -> bool:
        with self._symbol_switch_lock:
            sym = self.pending_symbol
            if not sym:
                return False
            if self._has_open_position():
                return False
            self.pending_symbol = None
            self._apply_symbol_switch(sym)
            return True

    def _attach_execution_stack(self):
        if self._execution_attached:
            return
        from backend.execution.execution_factory import ExecutionFactory
        from backend.execution.strategy_execution_adapter import StrategyExecutionAdapter
        from backend.adapters.execution.paper_execution_adapter import PaperExecutionAdapter
        from execution.system.execution_window import ExecutionWindow
        from backend.core.persistence.execution_journal import ExecutionJournal
        from trading_core.engines.dual_engine import DualEngine
        from trading_core.runtime.context import RuntimeContext

        self.executor = ExecutionFactory.build(self)

        self.execution_window = ExecutionWindow()
        self.execution_journal = ExecutionJournal()
        self.execution_orchestrator = ExecutionOrchestrator(
            execution_system=self.live_system,
            execution_state=self.live_system.execution_state,
            execution_lock=self.live_system.execution_lock,
            execution_window=self.execution_window,
            journal=self.execution_journal,
        )

        try:
            _strategy_loop = asyncio.get_event_loop()
        except RuntimeError:
            _strategy_loop = None

        context = RuntimeContext(self.config)

        class StrategyAccount:

            def __init__(self, balance=10000):
                self.balance = balance

            def get_balance(self):
                return self.balance

            def get_equity(self):
                return self.balance

            def get_state(self):
                class State:
                    current_day = None
                    blocked_until = None
                    daily_loss_count = 0

                return State()

            def register_loss(self, v):
                self.balance -= v

            def register_win(self, v):
                self.balance += v

            def reset_day(self, day):
                pass

            def daily_dd(self):
                return 0

        self.strategy_account = StrategyAccount()

        if self.mode == "paper":
            _strategy_exec_adapter = PaperExecutionAdapter()
        else:
            _strategy_exec_adapter = StrategyExecutionAdapter(
                session=self,
                loop=_strategy_loop,
            )

        self.strategy_engine = DualEngine(
            config=self.config,
            context=context,
            market=None,
            execution_adapter=_strategy_exec_adapter,
            account=self.strategy_account,
        )
        self.engine = self.executor
        self.live_system = getattr(self.executor, "execution_system", None)

        if self.live_system is None:
            raise Exception("❌ execution_system not attached to executor")

        self.engine = self.live_system
        print("ENGINE TYPE AT INIT:", type(self.engine))

        if hasattr(self.engine, "execution_state"):
            self.system_state.execution_state = self.engine.execution_state
            self.engine.execution_state.on_change = self.system_state._on_execution_state_change
            print("✅ Execution state listener attached (correct object)")

        self.data_feed = None
        self.runner = None
        self._execution_attached = True
        print(
            "[SESSION][EXEC_STACK]",
            "id=", self.id,
            "mode=", self.mode,
        )

    # =========================================================
    # lifecycle
    # =========================================================

    def build(self, engine, executor, data_feed, risk_system):
        """
        Attach all system components before start.
        """
        if engine is not None and hasattr(engine, "execute_plan"):
            self.engine = engine
        if executor is not None:
            self.executor = executor
        self.data_feed = data_feed
        self.risk_system = risk_system

        if data_feed is not None and type(data_feed).__name__ == "BinanceMarketAdapter":
            dsym = self._normalize_symbol(getattr(data_feed, "symbol", None))
            if dsym:
                self.symbol_contexts[dsym] = SymbolContext(symbol=dsym, market=data_feed)
                self.active_symbol = dsym
                self._write_config_symbol(dsym)

        self.status = self.STATUS_READY
        self._emit_system("SESSION_READY")

        print("[SESSION] build called, system_state =", self.system_state)

    # =========================================================

    def start(self):
        """
        Start trading system.
        """
        try:
            if self.status not in (
                self.STATUS_CREATED,
                self.STATUS_READY,
                self.STATUS_STOPPED,
            ):
                raise RuntimeError(
                    f"Cannot start session from state {self.status}"
                )

            if (
                not self._execution_attached
                and self.mode in ("live", "shadow")
            ):
                self._attach_execution_stack()

            # 1️⃣ SET STATUS
            self.status = self.STATUS_RUNNING
            self._emit_system("SESSION_STARTED")

            # 2️⃣ BIND SYSTEM STATE (no StateHub session binding!)
            self.system_state.bind()
            # 🔗 expose reconciliation hub to state engine
            self.system_state.reconciliation_hub = self.reconciliation_hub

            # 3️⃣ EMIT SNAPSHOT (schedule vào event loop của FastAPI)
            loop = asyncio.get_event_loop()
            loop.create_task(self.system_state.emit_snapshot())

            # 4️⃣ START HEARTBEAT (SystemStateEngine owns this)
            self.system_state.start_heartbeat()


            # ---- start subsystems ----
            if self.risk_system:
                self.risk_system.bind_execution(self.engine)

            # 🔥 START EXECUTION ENGINE (single execution graph)
            if self.engine and hasattr(self.engine, "start"):
                loop = asyncio.get_event_loop()
                loop.create_task(self.engine.start())
            
            print("[SESSION] started successfully")
            print(
                "[SESSION][START]",
                "id=", self.id,
                "mode=", self.mode,
                "has_reconciliation_hub=", hasattr(self, "reconciliation_hub"),
                "state_engine_has_recon=",
                hasattr(self.system_state, "state_hub")
            )

        except Exception as e:
            self.status = self.STATUS_ERROR
            self.last_error = str(e)
            self._emit_system("SESSION_ERROR", error=str(e))
            raise

    # =====================================================
    # POSITION SYNC
    # =====================================================

    def _sync_position_from_exchange(self):

        try:

            pos = self.executor._get_current_position("BTCUSDT")

            if not pos:
                return

            self.system_state.state.setdefault("execution", {})

            self.system_state.state["execution"]["positions"] = [{
                "symbol": "BTCUSDT",
                "side": pos["side"].upper(),
                "size": pos["size"]
            }]

            print(
                "🔄 POSITION SYNC:",
                pos["side"],
                pos["size"]
            )

        except Exception as e:

            print("⚠ POSITION SYNC FAILED:", e)

    # =========================================================

    def stop(self):
        """
        Stop trading system gracefully.
        """
        try:
            if self.mode == "backtest":
                svc = getattr(self, "backtest_service", None)
                if svc is not None and hasattr(svc, "stop"):
                    try:
                        svc.stop()
                    except Exception as e:
                        print("[BACKTEST STOP FLAG ERROR]", e)

            if self.engine:
                try:
                    loop = asyncio.get_event_loop()
                    if hasattr(self.engine, "stop"):
                        loop.create_task(self.engine.stop())
                except RuntimeError:
                    pass

            if self._supervisor:
                self._supervisor.stop()

            if self.data_feed:
                try:
                    self.data_feed.stop()
                except Exception as e:
                    print("[DATA_FEED STOP ERROR]", e)
                    
            if self.runner:
                self.runner.stop()

                if self.runner.is_alive():
                    self.runner.join(timeout=5)

            self.status = self.STATUS_STOPPED
            self._emit_system("SESSION_STOPPED")

        except Exception as e:
            self.status = self.STATUS_ERROR
            self.last_error = str(e)
            self._emit_system("SESSION_ERROR", error=str(e))
            raise

    # =========================================================
    # risk bridge
    # =========================================================

    def freeze(self, reason=None):
        self.status = self.STATUS_FROZEN
        self._emit_system("SESSION_FROZEN", reason=reason)

    def unfreeze(self):
        if self.status == self.STATUS_FROZEN:
            self.status = self.STATUS_RUNNING
            self._emit_system("SESSION_UNFROZEN")

    # =========================================================
    # health & monitoring
    # =========================================================

    def health_check(self):
        """
        Used by dashboard: pre-flight & runtime check.
        """
        return {
            "session_id": self.id,
            "status": self.status,
            "engine": self._safe_health(self.engine),
            "executor": self._safe_health(self.executor),
            "data_feed": self._safe_health(self.data_feed),
            "risk": self._safe_health(self.risk_system),
        }

    def snapshot(self):
        """
        Unified snapshot for app/dashboard.
        """
        return {
            "session_id": self.id,
            "mode": self.mode,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "risk": self._safe_snapshot(self.risk_system),
            "engine": self._safe_snapshot(self.engine),
            "executor": self._safe_snapshot(self.executor),
        }

    # =========================================================
    # internals
    # =========================================================

    def _emit_system(self, event_type, **payload):
        self.state_bus.publish({
            "type": event_type,
            "session_id": self.id,
            "ts": datetime.utcnow().isoformat(),
            "payload": payload,
        })

    def _safe_health(self, component):
        if component is None:
            return {"status": "DETACHED"}
        if hasattr(component, "health_check"):
            return component.health_check()
        return {"status": "UNKNOWN"}

    def _safe_snapshot(self, component):
        if component is None:
            return None
        if hasattr(component, "snapshot"):
            return component.snapshot()
        return None

    # =====================================================
    # Phase 5.2 – Internal Intent Injection
    # =====================================================
    async def inject_intent(self, intent):
        import asyncio
        print("[TRACE 1] INTENT", getattr(intent, "metadata", None))
        if self.execution_orchestrator is None:
            raise RuntimeError(
                "Session execution stack not started (start_session required)"
            )
        active_sym = self._normalize_symbol(getattr(self, "active_symbol", None))
        if not active_sym:
            active_sym = self._initial_symbol_from_config()
        intent_sym = self._normalize_symbol(getattr(intent, "symbol", None))
        if intent_sym and active_sym and intent_sym != active_sym:
            print("SYMBOL GUARD BLOCKED")
            print(f"intent_symbol={intent_sym}")
            print(f"active_symbol={active_sym}")
            return

        if intent.side in ("LONG", "SHORT"):
            self.refresh_daily_equity_risk_before_open()
            if getattr(self, "_daily_equity_dd_blocked", False):
                print("[DAILY_EQUITY_DD] BLOCKED open intent")
                return

        await asyncio.sleep(0.3)
        pos = None

        try:
            self.system_state.on_intent_submitted(intent)
        except Exception as e:
            print("⚠ INTENT SUBMIT STATE ERROR:", e)

        try:
            sync_engine = getattr(self.engine, "sync_engine", None)

            if sync_engine:
                pos_obj = None

                for p in sync_engine.position.get_all():
                    if p.symbol == intent.symbol and abs(p.size) > 1e-8:
                        pos_obj = p
                        break

                if pos_obj:
                    pos = {
                        "side": pos_obj.side,
                        "size": pos_obj.size
                    }
            # 🔥 REST FALLBACK (QUAN TRỌNG)
            if pos is None:
                try:
                    snapshot = self.engine.exchange.get_positions()
                    print("🔥 REST SNAPSHOT:", snapshot)

                    for p in snapshot:
                        if p.symbol == intent.symbol and p.size > 0:
                            pos = {
                                "side": p.side,
                                "size": p.size
                            }
                            break

                except Exception as e:
                    print("⚠ REST FALLBACK ERROR:", e)

            self.system_state.state.setdefault("execution", {})

            if pos and pos["size"] > 0:
                self.system_state.state["execution"]["positions"] = [{
                    "symbol": intent.symbol,
                    "side": pos["side"].upper(),
                    "size": pos["size"]
                }]
            else:
                self.system_state.state["execution"]["positions"] = []

            print("🔄 POSITION REFRESH:", pos)

        except Exception as e:
            print("⚠ POSITION REFRESH ERROR:", e)

        # =========================
        # READ CURRENT POSITION
        # =========================
        exec_state = self.system_state.state.get("execution", {})
        positions = exec_state.get("positions", [])

        from backend.core.execution_orchestrator import PositionState, PositionSide

        if positions:
            pos = positions[0]
            position = PositionState(
                side=PositionSide(pos["side"].lower()),
                size=pos["size"]
            )
        else:
            position = PositionState(
                side=PositionSide.FLAT,
                size=0
            )
        # 🔥 FIX QUAN TRỌNG: OPEN luôn coi như FLAT
        if intent.side in ["LONG", "SHORT"]:
            position = PositionState(
                side=PositionSide.FLAT,
                size=0
            )

        # =========================
        # BUILD ORCHESTRATOR INTENT
        # =========================
        from backend.core.execution_orchestrator import ExecutionIntent as OrchIntent

        if intent.side == "LONG":
            action = "open_long"
        elif intent.side == "SHORT":
            action = "open_short"
        else:
            action = "close"

        orch_intent = OrchIntent(
            action=action,
            symbol=intent.symbol,
            size=intent.qty,
            source=intent.source,
            metadata=getattr(intent, "metadata", {})
        )

        # =========================
        # ORCHESTRATOR DECISION
        # =========================
        from backend.core.execution_orchestrator import RiskState, SystemHealth

        risk = RiskState(breach=False, kill_switch=False)
        health = SystemHealth.NORMAL

        event = await self.execution_orchestrator.execute(intent)
        
        # =========================
        # UPDATE STATE
        # =========================
        if event:
            self.system_state.on_execution_event(event)
      
    # =====================================================
    # Strategy Control
    # =====================================================

    def set_strategy(self, name: str):

        allowed = ["long", "short", "dual"]

        if name not in allowed:
            raise ValueError("invalid strategy")

        if isinstance(self.config, dict):
            self.config["trade_mode"] = name
        else:
            self.config.trade_mode = name

        print(f"[SESSION] strategy switched to {name}")

    def get_strategy(self):

        if isinstance(self.config, dict):
            return self.config.get("trade_mode", "dual")

        return getattr(self.config, "trade_mode", "dual")

    # =====================================================
    # Risk Control
    # =====================================================

    def set_risk_config(self, payload: dict):

        allowed = [
            "risk_per_trade",
            "daily_dd_limit",
            "daily_stop_losses",
            "max_positions"
        ]

        for k, v in payload.items():

            if k not in allowed:
                continue

            self.risk_config[k] = v

        re = getattr(self, "risk_engine", None)
        if re is not None and hasattr(re, "set_daily_dd_limit_frac"):
            try:
                lim = self.risk_config.get("daily_dd_limit")
                if lim is not None:
                    re.set_daily_dd_limit_frac(float(lim))
            except Exception:
                pass

        print("[SESSION] risk config updated:", self.risk_config)


    def get_risk_config(self):

        return self.risk_config

    @staticmethod
    def _utc_calendar_date() -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _roll_daily_equity_risk_utc(self) -> None:
        today = self._utc_calendar_date()
        if self._daily_equity_utc_date != today:
            self._daily_equity_utc_date = today
            self._daily_start_equity = None
            self._daily_equity_started = False
            self._daily_equity_dd_blocked = False

    def _recompute_daily_equity_dd_block(self) -> None:
        if not self._daily_equity_started:
            self._daily_equity_dd_blocked = False
            return
        start = self._daily_start_equity
        if start is None or start <= 0:
            self._daily_equity_dd_blocked = False
            return
        try:
            eq = float(self.get_dynamic_equity())
        except Exception:
            return
        lim = float(self.risk_config.get("daily_dd_limit", 0.05))
        dd_frac = (eq - start) / start
        self._daily_equity_dd_blocked = dd_frac <= -lim

    def refresh_daily_equity_risk_before_open(self) -> None:
        """Call before new OPEN: roll UTC day and re-check vs live equity."""
        self._roll_daily_equity_risk_utc()
        self._recompute_daily_equity_dd_block()

    def on_execution_decision_for_daily_risk(self, decision: str) -> None:
        """OPENED/CLOSED from SystemStateEngine — anchor baseline on first trade of UTC day."""
        if decision not in ("OPENED", "CLOSED"):
            return
        self._roll_daily_equity_risk_utc()
        try:
            eq = float(self.get_dynamic_equity())
        except Exception:
            eq = 0.0
        if not self._daily_equity_started:
            self._daily_start_equity = eq
            self._daily_equity_started = True
        self._recompute_daily_equity_dd_block()

        re = getattr(self, "risk_engine", None)
        if re is not None and hasattr(re, "tick_daily_drawdown"):
            try:
                lim = float(self.risk_config.get("daily_dd_limit", 0.05))
                re.tick_daily_drawdown(eq, decision, lim)
            except Exception:
                pass

    def get_daily_equity_risk_snapshot(self) -> dict:
        self._roll_daily_equity_risk_utc()
        self._recompute_daily_equity_dd_block()
        try:
            eq = float(self.get_dynamic_equity())
        except Exception:
            eq = 0.0
        lim = float(self.risk_config.get("daily_dd_limit", 0.05))
        start = self._daily_start_equity
        dd_pct = None
        if self._daily_equity_started and start is not None and start > 0:
            dd_pct = ((eq - start) / start) * 100.0
        return {
            "utc_date": self._daily_equity_utc_date,
            "daily_started": self._daily_equity_started,
            "daily_start_equity": start,
            "current_equity": eq,
            "daily_drawdown_pct": dd_pct,
            "daily_limit_frac": lim,
            "daily_limit_pct": lim * 100.0,
            "blocked": self._daily_equity_dd_blocked,
        }

    def get_dynamic_equity(self):
        try:
            sync_engine = getattr(self.engine, "sync_engine", None)

            if sync_engine:
                sym = getattr(self, "active_symbol", None) or self._initial_symbol_from_config()
                quote = extract_quote_asset(sym)
                return sync_engine.account.get_equity(quote)

        except Exception:
            pass

        sa = getattr(self, "strategy_account", None)
        if sa is not None and hasattr(sa, "get_equity"):
            return sa.get_equity()
        return 0.0


def clear_live_runtime_refs(session) -> None:
    """
    After LiveService.stop (or equivalent), drop handles so a new adapter/runner
    can attach without stale WebSocket or callback lists. Does not clear config,
    execution graph, or risk state.
    """
    session.runner = None
    session.market = None
    session.data_feed = None
