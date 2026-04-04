# backend/core/execution_control_gate.py

class ExecutionControlGate:
    """
    Phase 5 – Controlled Execution Layer (Control Only)

    Responsibilities:
    - Enforce freeze_execution flag
    - Allow reduce-only close
    - Block new OPEN when frozen
    - Do not modify execution engine
    """

    def __init__(self, session):
        self.session = session

    def evaluate(self, intent):
        """
        Returns:
            (allowed: bool, reason: str | None)
        """

        # -------------------------------------------------
        # Read freeze state
        # -------------------------------------------------
        risk_state = self.session.system_state.state.get("risk", {})
        freeze = risk_state.get("state") == "FROZEN"

        # -------------------------------------------------
        # Read current positions
        # -------------------------------------------------
        execution_state = self.session.system_state.state.get("execution", {})
        positions = execution_state.get("positions", [])


        # =================================================
        # 2️⃣ Freeze enforcement
        # =================================================
        if freeze:
            # Block new OPEN when frozen
            if intent.type == "OPEN":
                return False, "execution_frozen"
        
        # -------------------------------------------------
        # CLOSE → validate symbol & size
        # -------------------------------------------------
        if intent.type == "CLOSE":
            symbol = intent.payload.get("symbol")

            position = next((p for p in positions if p.get("symbol") == symbol), None)

            if not position:
                return False, "no_position_to_close"

            requested_size = intent.payload.get("size")

            # Full close
            if requested_size is None:
                return True, None

            # Partial close validation
            if requested_size <= 0:
                return False, "invalid_close_size"

            if requested_size > position.get("size", 0):
                return False, "close_size_exceeds_position"

            return True, None

        # -------------------------------------------------
        # OPEN → validate size + max_positions
        # -------------------------------------------------
        if intent.type == "OPEN":

            size = intent.payload.get("size")
            symbol = intent.payload.get("symbol")

            if size is None:
                return False, "missing_size"

            if size <= 0:
                return False, "invalid_size"
            
            # Duplicate same-direction guard
            position = next((p for p in positions if p.get("symbol") == symbol), None)

            if position:
                if position.get("side") == intent.payload.get("side"):
                    return False, "duplicate_same_direction"

            return True, None

        # -----------------------------
        # max_positions enforcement
        # -----------------------------
        max_positions = getattr(self.session, "max_positions", 1)

        # Count current open positions
        open_symbols = {p.get("symbol") for p in positions}

        # If symbol already exists → allow (position increase logic later)
        if symbol in open_symbols:
            return True, None

        # New symbol
        if len(open_symbols) >= max_positions:
            return False, "max_positions_exceeded"

        return True, None

        # =================================================
        # 3️⃣ Default allow
        # =================================================
        return True, None
