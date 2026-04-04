# backend/execution/base_execution.py

from abc import ABC, abstractmethod


class BaseExecution(ABC):

    @abstractmethod
    async def execute(self, intent):
        pass
