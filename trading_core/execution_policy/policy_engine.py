from .quantity_policy import QuantityPolicy
from .transitions import TransitionValidator, TransitionType
from .decisions import PolicyDecision, PolicyDecisionType
from .intent_schema import IntentType


class ExecutionPolicyEngine:
    """
    Supreme authority of execution system.

    It decides:
    - ALLOW
    - REFUSE
    - FREEZE
    """

    def __init__(self):
        self.qty_policy = QuantityPolicy()
        self.transition_validator = TransitionValidator()

    def evaluate_intent(self, intent, current_net):

        # =========================
        # 1. EMERGENCY LAW
        # =========================

        if intent.type == IntentType.EMERGENCY:
            if intent.source == "system":
                return PolicyDecision(
                    decision=PolicyDecisionType.ALLOW,
                    reason="SYSTEM_EMERGENCY",
                    current=current_net,
                    target=current_net,
                    transition="EMERGENCY"
                )
            else:
                return PolicyDecision(
                    decision=PolicyDecisionType.FREEZE,
                    reason="ILLEGAL_EMERGENCY_SOURCE",
                    current=current_net
                )

        # =========================
        # 2. MAP INTENT → TARGET
        # =========================

        try:
            target = self.qty_policy.map_intent_to_target(intent, current_net)
        except Exception as e:
            # illegal intent → REFUSE
            return PolicyDecision(
                decision=PolicyDecisionType.REFUSE,
                reason=f"INTENT_INVALID: {e}",
                current=current_net
            )

        # =========================
        # 3. TRANSITION CLASSIFICATION
        # =========================

        try:
            transition = self.transition_validator.classify(current_net, target)
        except Exception as e:
            # illegal system state → FREEZE
            return PolicyDecision(
                decision=PolicyDecisionType.FREEZE,
                reason=f"ILLEGAL_TRANSITION: {e}",
                current=current_net
            )

        # =========================
        # 4. NOOP LAW
        # =========================

        if transition == TransitionType.NOOP:
            return PolicyDecision(
                decision=PolicyDecisionType.REFUSE,
                reason="NOOP / ALREADY_IN_STATE",
                current=current_net,
                target=target,
                transition=transition.value
            )

        # =========================
        # 5. CONSTITUTIONAL ALLOW
        # =========================

        return PolicyDecision(
            decision=PolicyDecisionType.ALLOW,
            reason="CONSTITUTIONAL",
            current=current_net,
            target=target,
            transition=transition.value
        )

    def verify_execution_result(self, target, final_net):

        # ===== normalize side =====
        final_side = (
            final_net.side.value
            if hasattr(final_net.side, "value")
            else final_net.side
        )

        final_size = float(final_net.size)
        target_size = float(target.qty)

        # ===== 1️⃣ SIDE CHECK (STRICT) =====
        if final_side != target.side:
            raise Exception("EXECUTION_RESULT_SIDE_MISMATCH")

        # ===== 2️⃣ SIZE CHECK (TOLERANT) =====
        # Binance precision tolerance
        tolerance = max(1e-6, target_size * 0.001)  
        # 0.1% tolerance or minimum 1e-6

        if abs(final_size - target_size) > tolerance:
            raise Exception(
                f"EXECUTION_RESULT_SIZE_MISMATCH "
                f"(expected={target_size}, actual={final_size})"
            )
