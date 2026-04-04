# =====================================================================
# ⚠ LEGACY DECISION ENGINE – NOT USED IN PRODUCTION FLOW
#
# This module belongs to the old execution decision engine.
# The current production architecture uses:
#   - backend/core/*
#   - execution/live_execution_system.py
#
# DO NOT import this module into backend/core or WS flow.
# =====================================================================
from backend.execution.types.intent import Intent
from backend.execution.types.execution_plan import ExecutionPlan
from backend.execution.orchestrator.execution_context import ExecutionContext
from backend.execution.decision.decision_table import evaluate_decision

class ExecutionOrchestrator:
    """
    Orchestrator = COORDINATOR
    - Không decision logic
    - Không mutate state
    - Không execution
    """

    def decide(self, intent: Intent, context: ExecutionContext) -> ExecutionPlan:
        decision_input = {
            "authority": context.authority,
            "position": context.position,
            "risk": context.risk,
            "health": context.health,
            "kill_switch": context.kill_switch,
            "intent": intent,
        }

        return evaluate_decision(decision_input)
