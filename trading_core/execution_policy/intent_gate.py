from .decisions import PolicyDecision, PolicyDecisionType
from .transitions import TransitionType


class IntentGate:

    def __init__(self, constitution, qty_policy, transitions):
        self.constitution = constitution
        self.qty_policy = qty_policy
        self.transitions = transitions

    def evaluate(self, intent, current_position):

        try:
            # 1. schema
            intent.validate_schema()

            # 2. authority
            self.constitution.validate_authority(intent)

            # 3. current legality
            self.constitution.validate_position(current_position)

            # 4. intent → target
            target = self.qty_policy.map_intent_to_target(intent)
            self.qty_policy.validate_target(target)

            # 5. transition classify
            transition = self.transitions.classify(current_position, target)

            # 6. NOOP law
            if transition == TransitionType.NOOP:
                return PolicyDecision(
                    decision=PolicyDecisionType.REFUSE,
                    reason="NOOP_ALREADY_IN_STATE",
                    current=current_position,
                    target=target,
                    transition=transition.value
                )

            # 7. illegal transition
            if transition == TransitionType.ILLEGAL:
                return PolicyDecision(
                    decision=PolicyDecisionType.REFUSE,
                    reason="ILLEGAL_TRANSITION",
                    current=current_position,
                    target=target,
                    transition=transition.value
                )

            # 8. ALLOW
            return PolicyDecision(
                decision=PolicyDecisionType.ALLOW,
                reason="OK",
                current=current_position,
                target=target,
                transition=transition.value
            )

        except Exception as e:
            # constitution / state violation → freeze
            return PolicyDecision(
                decision=PolicyDecisionType.FREEZE,
                reason=f"CONSTITUTION_VIOLATION: {e}",
                current=current_position,
                target=None,
                transition=None
            )
