import threading
import asyncio
import time
import queue

from backend.alerts.alert_manager import alert_manager
from backend.alerts.alert_types import Alert, AlertLevel, AlertSource


class LiveRunner(threading.Thread):

    def __init__(self, session, market):
        super().__init__(daemon=True)

        self.session = session
        self.market = market
        self.running = False
        self._intentional_stop = False
        self._candle_subscriber = None

        # event queue
        self.queue = queue.Queue(maxsize=1000)

    def _emit_system_engine_alert(self, message: str) -> None:
        try:
            sid = getattr(self.session, "id", None)
            alert_manager.create_alert(
                Alert(
                    level=AlertLevel.INFO,
                    source=AlertSource.SYSTEM,
                    message=message,
                    session=str(sid) if sid is not None else None,
                )
            )
        except Exception:
            pass

    def run(self):
        self._intentional_stop = False
        self.running = True
        self.session.status = "RUNNING"
        self._emit_system_engine_alert("Engine start")
        print("[LIVE RUNNER START]", f"runner_id={id(self)}")
        print("trade_mode =", getattr(self.session.config, "trade_mode", None))
        print("risk =", getattr(self.session.config, "risk_per_trade", None))
        
        engine = self.session.strategy_engine
        bus = self.session.state_bus

        # Bind per-session state engine (avoid global app.state dependency).
        self.session.state_engine = getattr(self.session, "system_state", None)

        
        def on_candle(i, row, df):
            if not self.running:
                return
            try:
                self.queue.put_nowait((i, row, df))
            except queue.Full:
                print("[LIVE RUNNER] queue overflow")    
                        
        # 🔌 subscribe qua market port
        self._candle_subscriber = on_candle
        self.market.subscribe_candle(on_candle)

        # ===== RUNNER LOOP =====
        while self.running:

            try:
                i, row, df = self.queue.get(timeout=1)
            except queue.Empty:
                continue
            # ===== SAFETY GATE (live dataframe validation) =====

            required_cols = [
                "ema200",
                "close_1h",
                "valid_long",
                "valid_short",
                "range_high",
                "range_low"
            ]

            if not all(col in df.columns for col in required_cols):
                continue


            # ===== CORE CALL (fault-tolerant) =====

            try:
                engine.on_bar(i, row, df)
            except Exception as e:
                print("[LIVE CORE ERROR]", e)
                continue


            # ===== STATE STREAM =====

            if engine.equity_tracker.curve:
                t, eq = engine.equity_tracker.curve[-1]
                state = bus.on_equity(t, eq)
            else:
                state = {}

            if engine.trades:
                last_trade = engine.trades[-1]
                state = bus.on_trade(last_trade)

            if getattr(self.session, "try_apply_pending_symbol", None):
                self.session.try_apply_pending_symbol()

        if self._intentional_stop:
            self._emit_system_engine_alert("Engine stop")

        sid = getattr(self.session, "id", None)
        print(
            "[LIVE RUNNER END]",
            f"runner_id={id(self)}",
            f"session={sid!r}",
        )

    def stop(self):
        self._intentional_stop = True
        self.running = False
        print(
            "[RUNNER STOP]",
            f"runner_id={id(self)}",
            "thread_alive=",
            self.is_alive(),
        )
        market = getattr(self, "market", None)
        cb = getattr(self, "_candle_subscriber", None)
        if market is not None and cb is not None and hasattr(
            market, "unsubscribe_candle"
        ):
            try:
                market.unsubscribe_candle(cb)
            except Exception:
                pass
        self._candle_subscriber = None
        print(
            "[RUNNER STOP]",
            f"runner_id={id(self)}",
            "after_unsubscribe thread_alive=",
            self.is_alive(),
        )
