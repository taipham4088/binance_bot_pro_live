from backend.execution.types.execution_state import ExecutionState


def build_snapshot(state: ExecutionState) -> dict:
    """
    Build FULL SNAPSHOT from ExecutionState
    Must contain ALL fields (Section 12)
    """

    return {
        "meta": state.meta.copy(),
        "authority": state.authority,
        "health": state.health,
        "execution_state": state.execution_state,
        "position": state.position.copy(),
        "risk": state.risk.copy(),
        "last_decision": state.last_decision.copy(),
    }
