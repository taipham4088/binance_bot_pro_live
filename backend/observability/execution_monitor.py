import time
from backend.observability.execution_recorder import record_execution
from dataclasses import dataclass, field
from typing import Optional, Dict
from collections import deque


@dataclass
class ExecutionTrace:

    symbol: str
    side: str
    size: float

    signal_price: float
    signal_time: float

    order_sent_time: Optional[float] = None
    exchange_ack_time: Optional[float] = None
    fill_time: Optional[float] = None

    fill_price: Optional[float] = None

    def mark_order_sent(self):
        self.order_sent_time = time.time()

    def mark_exchange_ack(self):
        self.exchange_ack_time = time.time()

    def mark_fill(self, price: float):
        self.fill_time = time.time()
        self.fill_price = price

    # ------------------------
    # analytics
    # ------------------------

    def signal_latency_ms(self):

        if self.order_sent_time is None or self.signal_time is None:
            return None

        return (self.order_sent_time - self.signal_time) * 1000


    def exchange_latency_ms(self):

        if self.exchange_ack_time is None or self.order_sent_time is None:
            return None

        return (self.exchange_ack_time - self.order_sent_time) * 1000


    def fill_latency_ms(self):

        if self.fill_time is None or self.exchange_ack_time is None:
            return None

        return (self.fill_time - self.exchange_ack_time) * 1000


    def total_latency_ms(self):
 
        if self.fill_time is None or self.signal_time is None:
            return None

        return (self.fill_time - self.signal_time) * 1000

    def slippage(self):

        if self.fill_price is None or self.signal_price is None:
            return None

        return self.fill_price - self.signal_price


class ExecutionMonitor:

    def __init__(self):
        # print("🔥 EXECUTION MONITOR INIT:", id(self))

        self.active: Dict[str, ExecutionTrace] = {}
        self.last_trace: Optional[ExecutionTrace] = None
        self.history = deque(maxlen=20)

    # ------------------------
    # lifecycle
    # ------------------------

    def start_trace(
        self,
        symbol: str,
        side: str,
        size: float,
        signal_price: Optional[float] = None
    ):

        trace = ExecutionTrace(
            symbol=symbol,
            side=side,
            size=size,
            signal_price=signal_price,
            signal_time=time.time()
        )

        key = f"{symbol}-{trace.signal_time}"

        self.active[key] = trace
        self.last_trace = trace

        return key

    def mark_order_sent(self, key):

        trace = self.active.get(key)

        if trace:
            trace.mark_order_sent()

    def mark_exchange_ack(self, key):

        trace = self.active.get(key)

        if trace:
            trace.mark_exchange_ack()

    def mark_fill(self, key, price):

        trace = self.active.get(key)

        if not trace:
            trace = self.last_trace

        if not trace:
            return

        # 🔥 KHÔNG overwrite nếu đã có timestamp từ EXECUTION event
        if trace.fill_time is None:
            trace.fill_time = time.time()

        trace.fill_price = price

        if trace.signal_price is None:
            trace.signal_price = price

        self.last_trace = trace

        # save history
        self.history.append({
            "time": time.time(),
            "symbol": trace.symbol,
            "side": trace.side,
            "size": trace.size,
            "signal_price": trace.signal_price,
            "fill_price": trace.fill_price,
            "slippage": trace.slippage(),
            "latency": trace.total_latency_ms()
        })
        
        if len(self.active) > 100:
            oldest = list(self.active.keys())[0]
            del self.active[oldest]
    # ------------------------
    # dashboard snapshot
    # ------------------------
    def on_execution_event(self, event: dict):

        if not event.get("symbol"):
            return

        # 🔥 luôn tạo trace mới cho mỗi execution
        trace = ExecutionTrace(
            symbol=event["symbol"],
            side=event.get("side"),
            size=event.get("size"),
            signal_price=event.get("signal_price"),
            signal_time=event.get("signal_time", time.time())
        )
        self.last_trace = trace
        # update optional timestamps
        if event.get("signal_time"):
            trace.signal_time = event.get("signal_time")

        if event.get("order_sent_time"):
            trace.order_sent_time = event.get("order_sent_time")

        if event.get("exchange_ack_time"):
            trace.exchange_ack_time = event.get("exchange_ack_time")

        # update fill info
        if event.get("fill_price") is not None:
            trace.fill_price = event.get("fill_price")

        if event.get("fill_time"):
            trace.fill_time = event.get("fill_time")
        elif trace.fill_time is None:
            trace.fill_time = time.time()      

        self.last_trace = trace

        data = self.snapshot()

        if data and data.get("fill_price") is not None:
            self.history.append(data)
            record_execution(data)

    
    def handle_trade(self, data: dict):

        if not data:
            return

        # print("[MONITOR] TRADE RECEIVED:", data)

        trade = {
            "time": data.get("ts"),
            "symbol": data.get("symbol"),
            "side": data.get("side"),
            "size": data.get("size"),
            "price": data.get("price"),
            "pnl": data.get("pnl", 0)
        }

        # ✅ lưu vào memory (nếu API dùng)
        self.history.append(trade)

        
    def snapshot(self):

        if not self.last_trace:
            return {}

        t = self.last_trace

        # fallback nếu signal_price chưa có
        signal_price = t.signal_price
        if signal_price is None:
            signal_price = t.fill_price

        slippage = None
        if signal_price is not None and t.fill_price is not None:
            slippage = t.fill_price - signal_price

        return {

            "symbol": t.symbol,
            "side": t.side,
            "size": t.size,

            "signal_price": signal_price,
            "fill_price": t.fill_price,

            "slippage": slippage,

            "signal_latency_ms": t.signal_latency_ms(),
            "exchange_latency_ms": t.exchange_latency_ms(),
            "fill_latency_ms": t.fill_latency_ms(),
            "total_latency_ms": t.total_latency_ms(),
        }

    def restore_position(self, symbol, side, size, price):

        print("[ExecutionMonitor] restore position")

        trace = ExecutionTrace(
            symbol=symbol,
            side=side,
            size=size,
            signal_price=price,
            signal_time=time.time()
        )

        trace.fill_price = price
        trace.fill_time = time.time()

        self.last_trace = trace