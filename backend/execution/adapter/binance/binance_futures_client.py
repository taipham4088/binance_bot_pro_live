from binance.um_futures import UMFutures


class BinanceFuturesClient:
    """
    Binance USDT-M Futures – READ ONLY
    """

    def __init__(self, api_key: str = None, api_secret: str = None, read_only: bool = False):
        self.read_only = read_only

        self._client = UMFutures(
            key=api_key,
            secret=api_secret,
    )


    # -----------------------------
    # ACCOUNT
    # -----------------------------
    def get_account(self):
        acc = self._client.account()
        return {
            "balance": float(acc["totalWalletBalance"]),
            "available": float(acc["availableBalance"]),
            "unrealized_pnl": float(acc["totalUnrealizedProfit"]),
        }

    # -----------------------------
    # POSITION (SINGLE SYMBOL / ALL)
    # -----------------------------
    def get_positions(self):
        positions = self._client.position_information()
        result = []

        for p in positions:
            size = float(p["positionAmt"])
            if size == 0:
                result.append({
                    "symbol": p["symbol"],
                    "side": None,
                    "size": 0,
                    "entry_price": 0,
                    "unrealized_pnl": 0,
                })
                continue

            side = "long" if size > 0 else "short"
            result.append({
                "symbol": p["symbol"],
                "side": side,
                "size": abs(size),
                "entry_price": float(p["entryPrice"]),
                "unrealized_pnl": float(p["unRealizedProfit"]),
            })

        return result
