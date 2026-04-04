import time
from .models import InternalOrder, InternalPosition, InternalBalance, OrderStatus


def map_order(event: dict) -> InternalOrder:
    return InternalOrder(
        order_id=str(event.get("i")),
        client_id=event.get("c"),
        symbol=event.get("s"),
        side=event.get("S"),
        position_side=event.get("ps"),
        order_type=event.get("o"),
        price=float(event.get("p")) if float(event.get("p", 0)) > 0 else None,
        qty=float(event.get("q")),
        filled=float(event.get("z")),
        status=OrderStatus(event.get("X")),
        update_ts=time.time()
    )


def map_position(p: dict) -> InternalPosition:

    # ===== WS ACCOUNT_UPDATE schema =====
    if "pa" in p:
        amt = float(p["pa"])
        symbol = p["s"]
        entry_price = float(p["ep"])
        unrealized = float(p.get("up", 0))
        leverage = float(p.get("l", 0) or 0)

        position_side = p.get("ps", "BOTH")

        if position_side == "LONG":
            side = "LONG"
        elif position_side == "SHORT":
            side = "SHORT"
        else:  # BOTH (one-way mode)
            if amt > 0:
                side = "LONG"
            elif amt < 0:
                side = "SHORT"
            else:
                side = "FLAT"

    # ===== REST snapshot schema =====
    else:
        amt = float(p.get("positionAmt", 0))
        symbol = p.get("symbol")
        entry_price = float(p.get("entryPrice", 0))

        unrealized = float(
            p.get("unrealizedProfit")
            or p.get("unRealizedProfit")
            or p.get("unrealizedPnl")
            or 0
        )

        leverage = float(p.get("leverage", 0) or 0)

        # 🔥 REST luôn suy ra side từ amount
        if amt > 0:
            side = "LONG"
        elif amt < 0:
            side = "SHORT"
        else:
            side = "FLAT"

    return InternalPosition(
        symbol=symbol,
        side=side,
        size=abs(amt),
        entry_price=entry_price,
        unrealized_pnl=unrealized,
        leverage=leverage,
        update_ts=time.time()
    )


def map_balance(b: dict) -> InternalBalance:
    # WS schema
    if "a" in b:
        asset = b["a"]
        wallet = b.get("wb", 0)
        available = b.get("cw", wallet)

    # REST schema
    else:
        asset = b["asset"]
        wallet = b.get("walletBalance") or b.get("balance") or 0
        available = b.get("availableBalance") or b.get("available") or wallet

    return InternalBalance(
        asset=asset,
        wallet=float(wallet),
        available=float(available),
        update_ts=time.time()
    )
