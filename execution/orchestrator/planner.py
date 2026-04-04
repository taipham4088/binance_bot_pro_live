# execution/orchestrator/planner.py

from execution.orchestrator.models import (
    ExecutionPlan,
    ExecutionStep,
    StepAction,
    TargetSide
)


class ExecutionPlanner:
    """
    Planner v2 (Target-based)

    - single symbol
    - no scale-in
    - explicit close → open on reverse
    - target is authoritative (from PolicyEngine)
    """

    def build_plan(self, positions: list, target) -> ExecutionPlan:
        steps: list[ExecutionStep] = []

        symbol = None
        if positions:
            symbol = positions[0].symbol
        elif hasattr(target, "symbol"):
            symbol = target.symbol
        else:
            raise Exception("SYMBOL_RESOLUTION_FAILED")
        target_side = self._parse_target_side(target)
        target_size = target.qty

        current = self._pick_current_position(positions)

        # ===== CASE 1: FLAT → OPEN =====
        if current is None and target_side != TargetSide.FLAT:
            steps.append(self._step_open(target_side, target_size, symbol))
            return ExecutionPlan(steps)

        # ===== CASE 2: HAVE → FLAT (CLOSE) =====
        if current is not None and target_side == TargetSide.FLAT:
            steps.append(self._step_close(current))
            return ExecutionPlan(steps)

        # ===== CASE 3: SAME SIDE =====
        if current is not None and current.side == target_side:
            raise Exception(
                "Execution policy violation: scale-in forbidden at execution layer"
            )

        # ===== CASE 4: REVERSE =====
        if current is not None and current.side != target_side:
            steps.append(self._step_close(current))
            steps.append(self._step_open(target_side, target_size, symbol))
            return ExecutionPlan(steps)

        return ExecutionPlan([])

    # --------------------
    # helpers
    # --------------------

    def _pick_current_position(self, positions: list):
        if not positions:
            return None

        for p in positions:
            if getattr(p, "size", 0) != 0:
                return p

        return None

    def _parse_target_side(self, target) -> TargetSide:

        if target.qty is None or target.qty == 0:
            return TargetSide.FLAT

        side = target.side.upper()

        if side == "LONG":
            return TargetSide.LONG
        if side == "SHORT":
            return TargetSide.SHORT

        return TargetSide.FLAT

    def _step_close(self, position) -> ExecutionStep:
        return ExecutionStep(
            action=StepAction.CLOSE,
            side=position.side,
            qty=abs(position.size),
            reduce_only=True,
            symbol=position.symbol
        )

    def _step_open(self, target_side, qty, symbol) -> ExecutionStep:
        return ExecutionStep(
            action=StepAction.OPEN,
            side=target_side,
            qty=qty,
            reduce_only=False,
            symbol=symbol
        )
