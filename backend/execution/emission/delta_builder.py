from backend.execution.emission.json_patch import replace
from backend.execution.types.execution_state import ExecutionState


def build_delta(prev: ExecutionState, curr: ExecutionState) -> list:
    """
    Build JSON Patch DELTA
    One timeline step = one DELTA
    """

    patches = []

    if prev.execution_state != curr.execution_state:
        patches.append(
            replace("/execution_state", curr.execution_state)
        )

    if prev.last_decision != curr.last_decision:
        patches.append(
            replace("/last_decision", curr.last_decision)
        )

    if prev.meta != curr.meta:
        patches.append(
            replace("/meta", curr.meta)
        )

    return patches
