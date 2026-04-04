# execution/reconciliation/post_restart_guard.py

class PostRestartReconciliationGuard:
    """
    Verifies exchange truth after replay & recovery.
    Prevents READY if drift detected.
    """

    def __init__(self, execution_state, exchange_adapter, journal):
        self.execution_state = execution_state
        self.exchange = exchange_adapter
        self.journal = journal

    # ==========================================================
    # ENTRY
    # ==========================================================

    def verify(self):
        print("[POST-RESTART] Verifying exchange truth...")

        if self.execution_state.is_frozen():
            print("[POST-RESTART] System already frozen. Skipping verification.")
            return

        try:
            positions = self.exchange.client.futures_position_information()
            open_orders = self.exchange.client.futures_get_open_orders()
        except Exception as e:
            print("[POST-RESTART] Exchange query failed:", e)
            self.execution_state.freeze("Post-restart exchange query failure")
            return

        # ------------------------------------------------------
        # 1️⃣ Check open orders (should not exist after recovery)
        # ------------------------------------------------------
        if open_orders:
            print("[POST-RESTART] Unexpected open orders detected:", open_orders)
            self.execution_state.freeze("Unexpected open orders after restart")
            return

        # ------------------------------------------------------
        # 2️⃣ Check ghost positions
        # ------------------------------------------------------
        active_positions = [
            p for p in positions
            if abs(float(p.get("positionAmt", 0))) > 1e-8
        ]

        # If journal shows no active execution but exchange has position → freeze
        last_event = self.journal.get_last_event()

        if active_positions and (
            not last_event or
            last_event.get("event_type") not in (
                "STEP_OPEN_CONFIRMED",
                "EXECUTION_COMPLETED"
            )
        ):
            print("[POST-RESTART] Ghost position detected:", active_positions)
            self.execution_state.freeze("Ghost position detected after restart")
            return

        print("[POST-RESTART] Exchange verification passed.")
