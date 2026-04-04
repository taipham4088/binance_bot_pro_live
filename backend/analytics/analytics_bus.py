from threading import Lock
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

