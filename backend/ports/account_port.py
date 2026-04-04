from abc import ABC, abstractmethod

class AccountPort(ABC):

    @abstractmethod
    def get_balance(self):
        pass

    @abstractmethod
    def get_positions(self):
        pass
