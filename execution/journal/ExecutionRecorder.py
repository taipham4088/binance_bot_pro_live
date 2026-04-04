from collections import deque


class ExecutionRecord:
    def __init__(self, execution_id, intent=None):
        self.execution_id = execution_id
        self.intent = intent
        self.start_ts = None
        self.end_ts = None
        self.status = "RUNNING"

        self.phases = []
        self.steps = []
        self.orders = []
        self.anomalies = []
        self.events = []

        self.result = None

    def snapshot(self):
        return {
            "execution_id": self.execution_id,
            "intent": str(self.intent),
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "status": self.status,
            "phases": self.phases,
            "steps": self.steps,
            "orders": self.orders,
            "anomalies": self.anomalies,
            "result": self.result,
            "events": self.events[-200:],  # tail only
        }


class ExecutionRecorder:

    def __init__(self, max_history=50):
        self.active: ExecutionRecord | None = None
        self.history = deque(maxlen=max_history)

    # =====================================================
    # EVENT HANDLER
    # =====================================================

    def on_event(self, event):
        et = event.type
        eid = event.execution_id

        # ---------- lifecycle ----------

        if et == "ExecutionStarted":
            rec = ExecutionRecord(eid, intent=event.payload.get("intent"))
            rec.start_ts = event.ts
            self.active = rec

        elif et == "ExecutionFinished":
            if self.active and self.active.execution_id == eid:
                self.active.end_ts = event.ts
                self.active.status = "DONE"
                self.history.appendleft(self.active)
                self.active = None

        elif et == "ExecutionAborted":
            if self.active and self.active.execution_id == eid:
                self.active.end_ts = event.ts
                self.active.status = "ABORTED"
                self.active.result = event.payload
                self.history.appendleft(self.active)
                self.active = None

        # ---------- phase ----------

        elif et == "ExecutionPhaseChanged":
            if self.active:
                self.active.phases.append((event.ts, event.payload.get("phase")))

        # ---------- step / order ----------

        elif et == "ExecutionStepStarted":
            if self.active:
                self.active.steps.append({
                    "ts": event.ts,
                    "step": event.payload
                })

        elif et == "ExecutionOrderSent":
            if self.active:
                self.active.orders.append({
                    "ts": event.ts,
                    "order": event.payload
                })

        elif et == "ExecutionStepConfirmed":
            if self.active:
                self.active.steps.append({
                    "ts": event.ts,
                    "confirmed": event.payload
                })

        # ---------- anomalies ----------

        elif et == "ExecutionWindowAnomaly":
            if self.active:
                self.active.anomalies.append({
                    "ts": event.ts,
                    "drift": event.payload
                })

        # ---------- supervisor ----------

        elif et == "ExecutionFrozen":
            if self.active:
                self.active.status = "FROZEN"
                self.active.result = event.payload

        # ---------- raw event log ----------

        if self.active:
            self.active.events.append(event.to_dict())

    # =====================================================
    # SNAPSHOT API
    # =====================================================

    def get_active(self):
        return self.active.snapshot() if self.active else None

    def get_history(self, n=20):
        return [r.snapshot() for r in list(self.history)[:n]]

    def snapshot(self):
        return {
            "active": self.get_active(),
            "history": self.get_history()
        }

# Backward compatibility (temporary)
ExecutionJournal = ExecutionRecorder
