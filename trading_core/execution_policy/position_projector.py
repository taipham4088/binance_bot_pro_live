# trading_core/execution_policy/position_projector.py

from trading_core.execution_policy.net_position import NetPosition, PositionSide


class PositionProjectionError(Exception):
    pass


class NetPositionProjector:
    """
    Project raw exchange positions -> 1 NetPosition (FLAT / LONG / SHORT)

    Rules:
    - No position or total == 0  -> FLAT
    - All > 0                    -> LONG (sum)
    - All < 0                    -> SHORT (abs(sum))
    - Mixed signs                -> ERROR (hedge detected)
    """

    def project(self, raw_positions: list) -> NetPosition:

        if not raw_positions:
            return NetPosition(side=PositionSide.FLAT, size=0.0)

        amts = []

        for p in raw_positions:
 
            # ===== CASE 1: dict from exchange =====
            if isinstance(p, dict):
                try:
                    amt = float(p.get("positionAmt", 0))
                except Exception:
                    raise PositionProjectionError(f"Invalid positionAmt: {p}")

            # ===== CASE 2: internal PositionState =====
            elif hasattr(p, "size"):
                try:
                    amt = float(p.size)
                    if getattr(p, "side", None) == "SHORT":
                        amt = -abs(amt)
                except Exception:
                    raise PositionProjectionError(f"Invalid PositionState: {p}")

            else:
                raise PositionProjectionError(f"Unsupported position type: {p}")

            if amt != 0:
                amts.append(amt)

        if not amts:
            return NetPosition(side=PositionSide.FLAT, size=0.0)

        has_long = any(a > 0 for a in amts)
        has_short = any(a < 0 for a in amts)

        if has_long and has_short:
            raise PositionProjectionError("HEDGE_MODE_DETECTED")

        total = sum(amts)

        if total > 0:
            return NetPosition(side=PositionSide.LONG, size=round(abs(total), 10))

        if total < 0:
            return NetPosition(side=PositionSide.SHORT, size=round(abs(total), 10))

        return NetPosition(side=PositionSide.FLAT, size=0.0)
