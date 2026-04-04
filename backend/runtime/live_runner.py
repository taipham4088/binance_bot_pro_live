import threading
import asyncio
import time
import queue

class LiveRunner(threading.Thread):

    def __init__(self, session, market):
        super().__init__(daemon=True)

        self.session = session
        self.market = market
        self.running = False
        
        # event queue
        self.queue = queue.Queue(maxsize=1000)

    def run(self):
        self.running = True
        self.session.status = "RUNNING"
        
        engine = self.session.strategy_engine
        bus = self.session.state_bus

        # 🔥 bind state_engine into session for execution propagation
        self.session.state_engine = self.session.app.state.state_engine

        
        def on_candle(i, row, df):
            if not self.running:
                return
            try:
                self.queue.put_nowait((i, row, df))
            except queue.Full:
                print("[LIVE RUNNER] queue overflow")    
                        
        # 🔌 subscribe qua market port
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

    def stop(self):
        self.running = False
