from binance import AsyncClient, BinanceSocketManager
import asyncio

# 🔥 DEBUG SWITCH
DEBUG_WS = False

def log_ws(*args):
    if DEBUG_WS:
        print(*args)


class BinanceUserStream:
    def __init__(self, api_key, api_secret, on_event):
        self.api_key = api_key
        self.api_secret = api_secret
        self.on_event = on_event

        self.client = None
        self.bm = None
        self._task = None
        self._running = False

    async def start(self):
        if self._running:
            return

        self.client = await AsyncClient.create(
            self.api_key,
            self.api_secret,
            testnet=True
        )

        self.bm = BinanceSocketManager(self.client)
        socket = self.bm.futures_user_socket()

        self._running = True

        async def _listener():
            async with socket as stream:
                while self._running:
                    msg = await stream.recv()

                    # ❌ giảm spam
                    log_ws("🔥 WS RAW:", msg)

                    # ===== HANDLE ACCOUNT UPDATE =====
                    if msg.get("e") == "ACCOUNT_UPDATE":
                        account = msg.get("a", {})
                        positions = account.get("P", [])

                        for p in positions:
                            amt = float(p.get("pa", 0))
                            symbol = p.get("s")

                            if amt == 0:
                                event = {
                                    "type": "POSITION_UPDATE",
                                    "symbol": symbol,
                                    "side": None,
                                    "size": 0
                                }
                            else:
                                side = "LONG" if amt > 0 else "SHORT"
                                event = {
                                    "type": "POSITION_UPDATE",
                                    "symbol": symbol,
                                    "side": side,
                                    "size": abs(amt)
                                }

                            # ❌ giảm spam
                            log_ws("🔥 WS POSITION EVENT:", event)

                            # ✅ vẫn gửi event
                            self.on_event(event)

                    else:
                        self.on_event(msg)

        self._task = asyncio.create_task(_listener())
        print("[USER_STREAM] started")

    async def stop(self):
        self._running = False

        if self._task:
            self._task.cancel()

        if self.client:
            await self.client.close_connection()

        print("[USER_STREAM] stopped")