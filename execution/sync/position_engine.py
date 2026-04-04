from .models import PositionState
import time


class PositionEngine:

    def __init__(self):
        self.positions = {}  # key = symbol + side


    def apply_snapshot(self, positions):
        self.positions.clear()

        for p in positions:
            if abs(float(p.size)) < 1e-8:
                continue

            key = f"{p.symbol}:{p.side}"
            self.positions[key] = PositionState(
                symbol=p.symbol,
                side=p.side,
                size=p.size,
                entry_price=getattr(p, "entry_price", None),
                unrealized_pnl=getattr(p, "unrealized_pnl", 0.0),
                leverage=p.leverage,
                last_update=time.time()
            )

        return list(self.positions.values())

    def apply_event(self, p):
        print("APPLY EVENT SIZE:", p.size, "SIDE:", p.side)
        # CLOSE LOGIC
        if abs(float(p.size)) < 1e-8:
            # Detect real transition: previous position existed -> now flat.
            keys_to_delete = [
                k for k in list(self.positions.keys())
                if k.split(":")[0] == p.symbol
            ]

            previous_size = 0.0
            previous_side = None
            for k in keys_to_delete:
                old_pos = self.positions.get(k)
                if old_pos:
                    previous_size += abs(float(old_pos.size))
                    previous_side = old_pos.side or previous_side

            for k in keys_to_delete:
                del self.positions[k]

            if previous_size > 1e-8:
                return "CLOSED", {
                    "symbol": p.symbol,
                    "side": previous_side or p.side,
                    "previous_size": previous_size,
                    "close_price": getattr(p, "entry_price", 0),
                }

            return None, None

        # UPDATE / OPEN LOGIC
        key = f"{p.symbol}:{p.side}"

        old = self.positions.get(key)

        # 🔥 Preserve entry_price nếu event không có
        entry_price = getattr(p, "entry_price", None)
        if entry_price is None and old:
            entry_price = old.entry_price

        # 🔥 Preserve unrealized pnl nếu event không có
        unrealized_pnl = getattr(p, "unrealized_pnl", None)
        if unrealized_pnl is None and old:
            unrealized_pnl = old.unrealized_pnl

        self.positions[key] = PositionState(
            symbol=p.symbol,
            side=p.side,
            size=p.size,
            entry_price=entry_price,
            unrealized_pnl=unrealized_pnl,
            leverage=p.leverage,
            last_update=time.time()
        )

        # 🔥 always emit updated
        return "UPDATED", self.positions[key]

            
    # ===== STEP 4 VIEW =====
    def get_all(self):
        return list(self.positions.values())
