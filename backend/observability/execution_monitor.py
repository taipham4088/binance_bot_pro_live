import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional

from backend.alerts.alert_manager import alert_manager
from backend.alerts.alert_types import Alert, AlertLevel, AlertSource
from backend.analytics.session_publish_context import resolve_session_id_from_call_stack
from backend.observability.execution_recorder import init_db, record_execution
from backend.storage.mode_storage import mode_storage

_ensure_execution_db_lock = threading.Lock()
_initialized_execution_db_paths: set[str] = set()

_logger = logging.getLogger(__name__)

_HIGH_LATENCY_MS = 8000.0
_HIGH_LATENCY_COOLDOWN_SEC = 60.0


def _ensure_execution_history_schema(mode: str) -> None:
    """
    Ensure per-session execution.db exists under data/<session_id>/execution.db
    with execution_history table (same layout as execution_recorder.init_db / record_execution).
    """
    db_path = mode_storage.get_execution_path(mode)
    with _ensure_execution_db_lock:
        if db_path in _initialized_execution_db_paths:
            return

    init_db(mode)

    with _ensure_execution_db_lock:
        if db_path in _initialized_execution_db_paths:
            return
        _initialized_execution_db_paths.add(db_path)
        print(f"[ExecutionMonitor] schema initialized for session: {mode}")


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
    fee: Optional[float] = None
    strategy: Optional[str] = None

    # Observability (optional; populated from EXECUTION payload or inferred at snapshot)
    order_price: Optional[float] = None
    order_id: Optional[str] = None
    status: Optional[str] = None
    step: Optional[str] = None
    # Optional pipeline timestamp (ms); preferred over derived wall time for DB row `time`
    event_time_ms: Optional[int] = None

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
    """
    Execution traces and latency observability. Position OPEN/CLOSE/REVERSE
    trading notifications are emitted from TradeJournal only (avoid duplicate
    bus delivery vs analytics handle_event).
    """

    def __init__(self):
        # print("🔥 EXECUTION MONITOR INIT:", id(self))

        self.active: Dict[str, ExecutionTrace] = {}
        self.last_trace: Optional[ExecutionTrace] = None
        self.history = deque(maxlen=20)
        self._last_high_latency_alert_ts: float = 0.0

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
        raw_fee = event.get("fee")
        fee_val = None
        if raw_fee is not None:
            try:
                fee_val = float(raw_fee)
            except (TypeError, ValueError):
                fee_val = None

        trace = ExecutionTrace(
            symbol=event["symbol"],
            side=event.get("side"),
            size=event.get("size"),
            signal_price=event.get("signal_price"),
            signal_time=event.get("signal_time", time.time()),
            fee=fee_val,
            strategy=event.get("strategy"),
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

        if event.get("order_price") is not None:
            try:
                trace.order_price = float(event["order_price"])
            except (TypeError, ValueError):
                pass
        if event.get("order_id") is not None:
            trace.order_id = str(event["order_id"])
        if event.get("status") is not None:
            trace.status = str(event["status"])
        if event.get("step") is not None:
            trace.step = str(event["step"])

        if event.get("event_time_ms") is not None:
            try:
                trace.event_time_ms = int(event["event_time_ms"])
            except (TypeError, ValueError):
                pass
        elif event.get("timestamp") is not None:
            try:
                trace.event_time_ms = int(float(event["timestamp"]) * 1000)
            except (TypeError, ValueError):
                pass

        if trace.status is None and event.get("error"):
            trace.status = "error"

        self.last_trace = trace

        data = self.snapshot()

        if data:
            lat = data.get("total_latency_ms")
            if lat is not None and float(lat) >= _HIGH_LATENCY_MS:
                now = time.time()
                if now - self._last_high_latency_alert_ts >= _HIGH_LATENCY_COOLDOWN_SEC:
                    self._last_high_latency_alert_ts = now
                    mode = resolve_session_id_from_call_stack()
                    try:
                        alert_manager.create_alert(
                            Alert(
                                level=AlertLevel.WARNING,
                                source=AlertSource.MONITORING,
                                message=f"High latency total_latency_ms={float(lat):.1f}",
                                symbol=trace.symbol,
                                session=mode,
                            )
                        )
                    except Exception:
                        pass

        if data and data.get("fill_price") is not None:
            self.history.append(data)
            mode = resolve_session_id_from_call_stack()
            if not mode:
                _logger.warning(
                    "execution session unresolved; skipping record_execution (no stack-bound session)"
                )
                return
            _ensure_execution_history_schema(mode)
            record_execution(data, mode=mode)

    
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

        order_price = t.order_price
        if order_price is None and t.fill_price is not None:
            order_price = t.fill_price

        step = t.step
        if not step:
            step = "fill"

        status = t.status
        if not status:
            status = "success" if t.fill_price is not None else "unknown"

        event_time_ms = t.event_time_ms
        if event_time_ms is None:
            event_wall = t.fill_time or t.signal_time
            if event_wall is not None:
                try:
                    event_time_ms = int(float(event_wall) * 1000)
                except (TypeError, ValueError):
                    event_time_ms = None

        ts_sec = None
        if event_time_ms is not None:
            ts_sec = int(event_time_ms / 1000)

        out = {

            "symbol": t.symbol,
            "side": t.side,
            "size": t.size,

            "signal_price": signal_price,
            "order_price": order_price,
            "fill_price": t.fill_price,
            "fee": t.fee,

            "strategy": t.strategy,

            "slippage": slippage,

            "signal_latency_ms": t.signal_latency_ms(),
            "exchange_latency_ms": t.exchange_latency_ms(),
            "fill_latency_ms": t.fill_latency_ms(),
            "total_latency_ms": t.total_latency_ms(),

            "status": status,
            "step": step,
            "order_id": t.order_id,
        }
        if event_time_ms is not None:
            out["event_time_ms"] = event_time_ms
        if ts_sec is not None:
            out["timestamp"] = ts_sec
        return out

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