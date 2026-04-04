class PlannerPolicyGuard:

    def verify_plan(self, plan, transition_type: str):
        # pseudo:
        # if transition == REVERSE:
        #   assert first is CLOSE reduce-only
        #   assert confirmed flat before open
        # if transition == CLOSE:
        #   assert no open
        # if transition == OPEN:
        #   assert no close
        pass

    def verify_execution_result(self, expected, actual):
        if expected != actual:
            raise RuntimeError("EXECUTION_RESULT_VIOLATION")
