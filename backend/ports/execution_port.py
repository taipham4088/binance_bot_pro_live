from abc import ABC, abstractmethod

class ExecutionPort(ABC):

    @abstractmethod
    def send_order(self, order_intent):
        pass

    @abstractmethod
    def cancel_order(self, order_id: str):
        pass
