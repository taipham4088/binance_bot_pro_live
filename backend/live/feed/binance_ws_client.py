import json
import asyncio
import websockets
import time
from backend.runtime.exchange_config import exchange_config
from backend.observability.health_metrics import (
    record_ws_disconnect,
    record_ws_reconnect,
)


class BinanceWSClient:

    def __init__(self, symbol: str, timeframe: str, on_candle):
        self.symbol = symbol.lower()
        self.tf = timeframe
        self.on_candle = on_candle

        self.ws_url = exchange_config.get_ws_kline(
            self.symbol,
            self.tf
        )
        self.running = False

        # health metrics
        self.last_message_ts = 0
        self.reconnect_attempt = 0

    async def connect(self):
        self.running = True

        while self.running:
            disconnect_notified = False

            def _notify_disconnect() -> None:
                nonlocal disconnect_notified
                if disconnect_notified:
                    return
                disconnect_notified = True
                try:
                    record_ws_disconnect("binance_ws")
                except Exception:
                    pass

            try:
                prior_attempts = self.reconnect_attempt
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5
                ) as ws:

                    print("[BINANCE WS] connected")

                    self.reconnect_attempt = 0
                    if prior_attempts > 0:
                        try:
                            record_ws_reconnect("binance_ws")
                        except Exception:
                            pass

                    await self._listen(ws)

            except Exception as e:

                _notify_disconnect()

                self.reconnect_attempt += 1
                wait = min(30, 2 ** self.reconnect_attempt)

                print(f"[BINANCE WS] disconnected: {e}")
                print(f"[BINANCE WS] reconnect in {wait}s")

                await asyncio.sleep(wait)

            else:
                if self.running:
                    _notify_disconnect()

    async def _listen(self, ws):

        async for msg in ws:

            self.last_message_ts = time.time()

            try:
                data = json.loads(msg)

                if "k" not in data:
                    continue

                k = data["k"]

                candle = {
                    "time": k["t"] / 1000,
                    "open": float(k["o"]),
                    "high": float(k["h"]),
                    "low": float(k["l"]),
                    "close": float(k["c"]),
                    "volume": float(k["v"]),
                    "is_closed": k["x"]
                }

                # chỉ emit khi nến đóng
                if candle["is_closed"]:
                    await self.on_candle(candle)

            except Exception as e:
                print("[BINANCE WS] candle parse error:", e)

    def stop(self):
        self.running = False
    
    def health_check(self):

        if not self.running:
            return {"status": "STOPPED"}

        now = time.time()

        if now - self.last_message_ts > 60:
            return {"status": "STALE"}

        return {"status": "CONNECTED"}
        
