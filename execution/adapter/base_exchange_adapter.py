# execution/adapter/base_exchange_adapter.py

from abc import ABC, abstractmethod


class BaseExchangeAdapter(ABC):

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Return exchange identifier (e.g. 'binance', 'okx')."""
        pass

    @abstractmethod
    async def open_position(self, symbol: str, side: str, quantity: float):
        pass

    @abstractmethod
    async def close_position(self, symbol: str, quantity: float):
        pass

    @abstractmethod
    async def fetch_position(self, symbol: str):
        pass

    @abstractmethod
    def start_user_stream(self):
        pass

    @abstractmethod
    def stop_user_stream(self):
        pass
