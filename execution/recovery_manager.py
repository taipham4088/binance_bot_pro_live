# execution/recovery_manager.py

from backend.core.persistence.execution_journal import ExecutionJournal


class RecoveryManager:
    """
    Production-grade deterministic recovery manager.
    Handles unfinished executions after crash.
    """

    def __init__(self,
                 execution_state,
                 exchange_adapter,
                 journal: ExecutionJournal,
                 session_id: str = "default"):

        self.execution_state = execution_state
        self.exchange = exchange_adapter
        self.journal = journal
        self.session_id = session_id

    # ==========================================================
    # PUBLIC ENTRY
    # ==========================================================

    def recover_execution(self, execution_id: str):
        print(f"[RECOVERY] Resolving execution: {execution_id}")

        events = self.journal.load_by_execution_id(execution_id)

        if not events:
            print("[RECOVERY] No events found.")
            return

        last_event = events[-1]
        last_type = last_event.get("event_type")
        last_order_id = last_event.get("order_id")

        print(f"[RECOVERY] Last event: {last_type}")

        if last_type in ("STEP_CLOSE_SENT", "STEP_OPEN_SENT"):
            self._resolve_sent_step(execution_id, last_type, last_order_id)

        elif last_type == "STEP_CLOSE_CONFIRMED":
            print("[RECOVERY] CLOSE confirmed before crash → waiting for OPEN.")
            # Orchestrator will handle next step

        elif last_type == "STEP_OPEN_CONFIRMED":
            print("[RECOVERY] OPEN already confirmed → marking execution completed.")
            self._mark_execution_completed(execution_id)

        elif last_type == "EXECUTION_STARTED":
            print("[RECOVERY] Execution started but no steps sent.")
            self._mark_execution_failed(execution_id, "Execution interrupted before step")

        else:
            print("[RECOVERY] Unknown state → freezing.")
            self.execution_state.freeze("Unknown recovery state")

    # ==========================================================
    # STEP RESOLUTION
    # ==========================================================

    def _resolve_sent_step(self, execution_id: str, step_type: str, order_id: str):

        if not order_id:
            print("[RECOVERY] No order_id found → freeze.")
            self.execution_state.freeze("Missing order_id in recovery")
            return

        try:
            order = self.exchange.client.futures_get_order(
                symbol=self.exchange.symbol,
                orderId=order_id
            )
        except Exception as e:
            print("[RECOVERY] Order query failed:", e)
            self.execution_state.freeze("Order query failure during recovery")
            return

        status = order.get("status")
        print(f"[RECOVERY] Exchange order status: {status}")

        if status == "FILLED":
            print("[RECOVERY] Order filled → confirming step.")
            self._confirm_step(execution_id, step_type, order_id)

        elif status in ("NEW", "PARTIALLY_FILLED"):
            print("[RECOVERY] Order still open → cancelling.")
            try:
                self.exchange.client.futures_cancel_order(
                    symbol=self.exchange.symbol,
                    orderId=order_id
                )
            except Exception as e:
                print("[RECOVERY] Cancel failed:", e)
                self.execution_state.freeze("Cancel failure during recovery")

        elif status in ("CANCELED", "REJECTED", "EXPIRED"):
            print("[RECOVERY] Order closed by exchange → verify position.")
            self._verify_position()

        else:
            print("[RECOVERY] Unknown exchange status → freeze.")
            self.execution_state.freeze("Unknown exchange order status")

    # ==========================================================
    # HELPERS
    # ==========================================================

    def _confirm_step(self, execution_id: str, step_type: str, order_id: str):

        confirm_event = (
            "STEP_CLOSE_CONFIRMED"
            if step_type == "STEP_CLOSE_SENT"
            else "STEP_OPEN_CONFIRMED"
        )

        self.journal.append_event(
            session_id=self.session_id,
            event_type=confirm_event,
            execution_id=execution_id,
            order_id=order_id,
            status="RECOVERED_CONFIRM"
        )

    def _mark_execution_completed(self, execution_id: str):
        self.journal.append_event(
            session_id=self.session_id,
            event_type="EXECUTION_COMPLETED",
            execution_id=execution_id
        )

    def _mark_execution_failed(self, execution_id: str, reason: str):
        self.journal.append_event(
            session_id=self.session_id,
            event_type="EXECUTION_FAILED",
            execution_id=execution_id,
            error_type="RECOVERY",
            error_message=reason
        )

    def _verify_position(self):
        try:
            positions = self.exchange.client.futures_position_information()
            print("[RECOVERY] Position snapshot:", positions)
        except Exception as e:
            print("[RECOVERY] Position verification failed:", e)
            self.execution_state.freeze("Position verify failure")
