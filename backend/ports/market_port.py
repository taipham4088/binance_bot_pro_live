from abc import ABC, abstractmethod

class MarketPort(ABC):

    @abstractmethod
    def get_latest_candle(self, symbol: str, tf: str):
        pass

    @abstractmethod
    def subscribe_candle(self, symbol: str, tf: str, callback):
        pass
