# execution/metadata_registry.py

from typing import Dict, Any, Optional
import threading


class ExecutionMetadataRegistry:
    """
    Deterministic metadata registry

    execution_id -> metadata

    Production safe:
    - thread safe
    - minimal memory
    - deterministic lookup
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}

    def register(self, execution_id: str, metadata: Dict[str, Any]) -> None:
        if not execution_id:
            return

        if not metadata:
            return

        with self._lock:
            self._data[execution_id] = metadata

        print("[METADATA REGISTER]", execution_id, metadata)

    def pop(self, execution_id: str) -> Optional[Dict[str, Any]]:
        if not execution_id:
            return None

        with self._lock:
            metadata = self._data.pop(execution_id, None)

        print("[METADATA POP]", execution_id, metadata)

        return metadata

    def get(self, execution_id: str) -> Optional[Dict[str, Any]]:
        if not execution_id:
            return None

        with self._lock:
            return self._data.get(execution_id)


# singleton
execution_metadata_registry = ExecutionMetadataRegistry()