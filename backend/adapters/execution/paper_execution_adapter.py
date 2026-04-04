from backend.ports.market_port import MarketPort
from backend.ports.execution_port import ExecutionPort
from backend.ports.account_port import AccountPort
from backend.adapters.execution.sim_executor import SimExecutor


class PaperExecutionAdapter(ExecutionPort):

    def __init__(self):
        self.executor = SimExecutor()
        self.orders = []

    def send_order(self, order_intent: dict):
        """
        order_intent: do DualEngine phát sinh
        """
        result = self.executor.execute(order_intent)
        self.orders.append(result)
        return result

    def cancel_order(self, order_id: str):
        # paper mode: chưa hỗ trợ cancel
        return {
            "status": "IGNORED",
            "order_id": order_id
        }
