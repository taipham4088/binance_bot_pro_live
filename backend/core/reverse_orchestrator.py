# backend/core/reverse_orchestrator.py

class ReverseOrchestrator:
    """
    Phase 5.1 – Explicit Reverse Orchestration

    LONG → SHORT:
        1. Reduce-only close
        2. Confirm flat
        3. Open new side
    """

    def __init__(self, session):
        self.session = session

    def check_reverse(self, intent):
        """
        Returns:
            ("normal", None)
            ("close_first", close_intent)
        """

        if intent.type != "OPEN":
            return "normal", None

        execution_state = self.session.system_state.state.get("execution", {})
        positions = execution_state.get("positions", [])

        if not positions:
            return "normal", None

        current_pos = positions[0]
        current_side = current_pos.get("side")
        new_side = intent.payload.get("side")

        if current_side == new_side:
            return "normal", None

        # Opposite side detected → must close first
        close_intent = {
            "type": "CLOSE",
            "payload": {
                "symbol": intent.payload.get("symbol")
            }
        }

        # Store pending reverse intent
        self.session.pending_reverse_intent = intent

        return "close_first", close_intent
