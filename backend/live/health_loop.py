# backend/live/health_loop.py
from execution.state.execution_state import ExecutionStatus
import asyncio
import time
from backend.observability.health_metrics import record_heartbeat

class HealthLoop:

    def __init__(
        self,
        state_engine,
        sync_engine,
        execution_state, 
        interval_sec: int = 5,
        ws_timeout_sec: int = 20,
    ):
        self.state_engine = state_engine
        self.sync_engine = sync_engine
        self.execution_state = execution_state
        self.interval_sec = interval_sec
        self.ws_timeout_sec = ws_timeout_sec
        self._running = False
        # health thresholds
        self.warning_threshold = 3
        self.critical_threshold = 6
        self.error_count = 0

    async def start(self):
        self._running = True

        try:
            while self._running:

                try:

                    # =========================
                    # HEARTBEAT
                    # =========================
                    self.state_engine._on_heartbeat()
                    record_heartbeat()

                    # =========================
                    # EXECUTION STATE CHECK
                    # =========================
                    status = self.execution_state.status

                    if status == ExecutionStatus.FROZEN:
                        print("[HEALTH] system frozen")
                    else:
                        # system healthy
                        self.error_count = 0

                except Exception as e:

                    self.error_count += 1

                    print("[HEALTH] error:", e)

                    if self.error_count >= self.critical_threshold:

                        print("[HEALTH] critical failure → freeze")

                        try:
                            self.execution_state.freeze("health loop critical failure")
                        except Exception:
                            pass

                    elif self.error_count >= self.warning_threshold:

                        print("[HEALTH] degraded health detected")

                await asyncio.sleep(self.interval_sec)

        except asyncio.CancelledError:
            print("[HEALTH] cancelled")
            raise

    def stop(self):
        self._running = False
