from trading_core.analytics.streaming.equity_streamer import StreamingEquityStateEngine
from trading_core.analytics.streaming.side_bias_streamer import StreamingSideBiasEngine


class SystemStateBus:
    """
    Central realtime state aggregator
    """

    def __init__(self):
        self.equity_engine = StreamingEquityStateEngine()
        self.side_engine = StreamingSideBiasEngine()

        self._subscribers = []   # ✅ THÊM DÒNG NÀY

        self.state = {
            "equity_state": "NEUTRAL",
            "side_bias": "NONE",
            "drawdown": 0.0
        }

    def on_equity(self, time, equity):

        eq_state = self.equity_engine.on_equity(time, equity)

        self.state["equity_state"] = eq_state
        self.state["drawdown"] = self.equity_engine.last_dd

        return self.state

    def on_trade(self, trade):

        side_state = self.side_engine.on_trade(trade)
        self.state["side_bias"] = side_state

        return self.state

    def on_status(self, updates: dict):
        """Merge ad-hoc keys (e.g. backtest progress) into broadcastable state."""
        if not updates:
            return self.state
        self.state.update(updates)
        return self.state

    def snapshot(self):
        return dict(self.state)

    # =========================
    # ADAPTER (event → state)
    # =========================

    def subscribe(self, callback):
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback):
        if callback in self._subscribers:
            self._subscribers.remove(callback)


    def publish(self, event):
        """
        Adapter để tương thích execution system cũ.
        Hiện tại broadcast event cho app layer (StateHub, ws, notification…)
        """

        # 🔔 broadcast lên app / dashboard
        for cb in list(self._subscribers):
            try:
                cb(event)
            except Exception as e:
                print("[SystemStateBus] subscriber error:", e)

        # TODO: sau này map event → on_equity / on_trade / snapshot store
    
