from backend.execution.adapter.paper_adapter import PaperExecutionAdapter


class AdapterRegistry:
    def __init__(self):
        self._adapters = {
            "paper": PaperExecutionAdapter(),
        }

    def get(self, mode: str):
        return self._adapters[mode]
