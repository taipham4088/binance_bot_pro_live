from enum import Enum
from dataclasses import dataclass
from typing import Optional

from backend.control_plane.hooks_bridge.execution_hooks_bridge import HookResult


# ============================================================
# Lifecycle States
# ============================================================

class LifecycleState(str, Enum):
    VALIDATING = "VALIDATING"
    STOPPING_BOT = "STOPPING_BOT"
    CLOSING_POSITION = "CLOSING_POSITION"
    CANCELING_ORDERS = "CANCELING_ORDERS"
    RESETTING_RUNTIME = "RESETTING_RUNTIME"
    APPLYING_CONFIG = "APPLYING_CONFIG"
    STARTING_BOT = "STARTING_BOT"
    POST_SWITCH_VERIFY = "POST_SWITCH_VERIFY"
    DONE = "DONE"
    FAILED = "FAILED"


# ============================================================
# Context passed through lifecycle
# ============================================================

@dataclass
class LifecycleContext:
    session_id: str
    new_config: dict
    current_state: LifecycleState = LifecycleState.VALIDATING
    error: Optional[str] = None


# ============================================================
# Lifecycle Orchestrator
# ============================================================

class LifecycleOrchestrator:
    """
    Deterministic lifecycle runner.
    No async. No job. No retry loop here.
    """

    def __init__(self, hooks):
        self.hooks = hooks

    # --------------------------------------------------------
    # Run one lifecycle step
    # --------------------------------------------------------

    def step(self, ctx: LifecycleContext) -> LifecycleContext:

        state = ctx.current_state

        if state == LifecycleState.VALIDATING:
            return self._next(ctx, LifecycleState.STOPPING_BOT)

        if state == LifecycleState.STOPPING_BOT:
            return self._call(
                ctx,
                self.hooks.stop_bot,
                LifecycleState.CLOSING_POSITION
            )

        if state == LifecycleState.CLOSING_POSITION:
            return self._call(
                ctx,
                self.hooks.close_all_positions,
                LifecycleState.CANCELING_ORDERS
            )

        if state == LifecycleState.CANCELING_ORDERS:
            return self._call(
                ctx,
                self.hooks.cancel_all_orders,
                LifecycleState.RESETTING_RUNTIME
            )

        if state == LifecycleState.RESETTING_RUNTIME:
            return self._call(
                ctx,
                self.hooks.reset_runtime,
                LifecycleState.APPLYING_CONFIG
            )

        if state == LifecycleState.APPLYING_CONFIG:
            return self._call_with_config(
                ctx,
                self.hooks.apply_config,
                LifecycleState.STARTING_BOT
            )

        if state == LifecycleState.STARTING_BOT:
            return self._call(
                ctx,
                self.hooks.start_bot,
                LifecycleState.POST_SWITCH_VERIFY
            )

        if state == LifecycleState.POST_SWITCH_VERIFY:
            return self._call(
                ctx,
                self.hooks.post_switch_verify,
                LifecycleState.DONE
            )

        return ctx

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------

    def _call(self, ctx, fn, next_state):
        result: HookResult = fn(ctx.session_id)

        if result.success:
            return self._next(ctx, next_state)

        return self._fail(ctx, result)

    def _call_with_config(self, ctx, fn, next_state):
        result: HookResult = fn(ctx.session_id, ctx.new_config)

        if result.success:
            return self._next(ctx, next_state)

        return self._fail(ctx, result)

    def _next(self, ctx, next_state):
        ctx.current_state = next_state
        return ctx

    def _fail(self, ctx, result: HookResult):
        ctx.current_state = LifecycleState.FAILED
        ctx.error = result.message
        return ctx
