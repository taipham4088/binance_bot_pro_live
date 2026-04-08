from threading import Lock

from backend.runtime.runtime_config import runtime_config


def _enrich_analytics_payload(event_type, data):
    """
    Attach active strategy from runtime_config when publishers omit it.
    Dashboard sets runtime_config["strategy"] via /api/control/strategy.
    """
    if not isinstance(data, dict):
        return data
    if event_type not in (
        "EXECUTION",
        "TRADE",
        "POSITION_OPEN",
        "POSITION_CLOSE",
    ):
        return data
    if data.get("strategy"):
        return data
    s = runtime_config.get("strategy")
    if not s:
        return data
    out = dict(data)
    out["strategy"] = s
    return out


class AnalyticsEventBus:
    """
    Event bus để truyền execution events sang analytics layer.
    """

    def __init__(self):

        self.subscribers = []
        self.lock = Lock()

    def subscribe(self, handler):

        with self.lock:
            if handler not in self.subscribers:
                self.subscribers.append(handler)

    def unsubscribe(self, handler):

        if handler in self.subscribers:
            self.subscribers.remove(handler)

    def publish(self, event_type, data):
        """
        Gửi event đến tất cả subscribers.
        """
        # Debug only
        # print(f"[BUS] event={event_type} data={data}")

        data = _enrich_analytics_payload(event_type, data)

        with self.lock:
            handlers = list(self.subscribers)

        for handler in handlers:
            try:

                # EXECUTION
                if event_type == "EXECUTION":
                    if hasattr(handler, "on_execution_event"):
                        handler.on_execution_event(data)

                # TRADE
                elif event_type == "TRADE":
                    if hasattr(handler, "handle_trade"):
                        handler.handle_trade(data)

                # fallback
                elif hasattr(handler, "handle_event"):
                    handler.handle_event(event_type, data)

            except Exception as e:
                print(f"[AnalyticsBus ERROR] {e}")
# ✅ đặt ở đây (không indent)
analytics_bus = AnalyticsEventBus()

