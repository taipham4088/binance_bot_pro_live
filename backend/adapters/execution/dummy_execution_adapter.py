import asyncio
from backend.ports.execution_port import ExecutionPort


class DummyExecutionAdapter(ExecutionPort):

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    def send_order(self, order_intent):
        print("[DUMMY EXECUTION] forward intent to orchestrator")
        asyncio.create_task(
            self.orchestrator.submit_intent(order_intent)
        )
        return {"status": "INTENT_SUBMITTED", "order": order_intent}

    def cancel_order(self, order_id: str):
        return {"status": "IGNORED", "order_id": order_id}
