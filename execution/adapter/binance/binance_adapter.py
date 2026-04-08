from __future__ import annotations

import asyncio
import time
from typing import Optional
from binance import Client
from .trade_client import BinanceTradeClient
from .user_stream import BinanceUserStream
from .rest_sync import BinanceRestSync
from . import mapper
from execution.adapter.base_exchange_adapter import BaseExchangeAdapter
from execution.fill_result import FillResult
from backend.runtime.exchange_config import exchange_config


class _BracketAwareTradeClient(BinanceTradeClient):
    """
    After orchestrator MARKET entry fills, schedule protective STOP / TP on the event loop.
    Suppressed when BinanceExecutionAdapter.open_position calls place_order (brackets placed there).
    """

    def __init__(self, client, execution_state, execution_lock, symbol: str, adapter):
        super().__init__(client, execution_state, execution_lock, symbol)
        self._adapter = adapter

    def place_order(self, *, execution_id=None, **kwargs):
        resp = super().place_order(execution_id=execution_id, **kwargs)
        try:
            if getattr(self._adapter, "_bracket_hook_suppressed", False):
                return resp
            if kwargs.get("type") != "MARKET" or kwargs.get("reduceOnly"):
                return resp
            qty = float(resp.get("executedQty", 0) or 0)
            if qty <= 0:
                return resp
            sym = kwargs.get("symbol") or self.symbol
            bin_side = kwargs.get("side")
            if bin_side not in ("BUY", "SELL"):
                return resp
            pos_side = "LONG" if bin_side == "BUY" else "SHORT"

            md_snapshot = {}
            es = self.execution_state
            if es is not None and hasattr(es, "get_metadata"):
                md_snapshot = dict(es.get_metadata(execution_id or ""))

            async def _run():
                await self._adapter._maybe_place_brackets(
                    sym, pos_side, qty, execution_id, metadata=md_snapshot
                )

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_run())
            except RuntimeError:
                pass
        except Exception as e:
            print("[BRACKET_HOOK_ERROR]", e)
        return resp


class ExchangePositionView:
    def __init__(self, symbol: str, side: str, size: float):
        self.symbol = symbol
        self.side = side
        self.size = size


class BinanceExecutionAdapter(BaseExchangeAdapter):
    """
    Execution adapter cho Binance Futures (testnet).

    - trade client đã được GUARD bởi ExecutionLock
    - adapter không được phép gửi lệnh trực tiếp qua self.client
    """

    def __init__(self, api_key: str, api_secret: str, sync_engine,
                execution_state, execution_lock, symbol: str):

        # ===== RAW CLIENT =====
        from binance.exceptions import BinanceAPIException

        for attempt in range(3):
            try:
                self.client = Client(api_key, api_secret, testnet=True)
                self.client.FUTURES_URL = f"{exchange_config.rest_url}/fapi"

                # 🔥 sync server time
                server_time = self.client.get_server_time()
                self.client.timestamp_offset = (
                    server_time["serverTime"]
                    - int(time.time() * 1000)
                )

                print("[BINANCE] Connected OK")
                break

            except Exception as e:
                print(f"[BINANCE INIT RETRY {attempt+1}/3]", e)
                time.sleep(0.5)

        else:
            raise Exception("Binance initialization failed")

        # ===== SYSTEM CONTEXT =====
        self.execution_state = execution_state
        self.execution_lock = execution_lock
        self.symbol = symbol
        self.sync_engine = sync_engine

        # ===== GUARDED TRADE CLIENT (bracket hook for orchestrator MARKET entries) =====
        self._bracket_hook_suppressed = False
        self.trade = _BracketAwareTradeClient(
            self.client,
            execution_state,
            execution_lock,
            symbol,
            self,
        )
        # ===== SYNC & STREAM =====
        self.sync = BinanceRestSync(self.client)
        self.stream = BinanceUserStream(
            api_key,
            api_secret,
            sync_engine.on_user_event
        )

    # =====================================================
    # USER STREAM
    # =====================================================

    async def start_user_stream(self):
        await self.stream.start()

        # 🔥 FORCE SNAPSHOT AFTER STREAM START
        try:
            snapshot = self.get_snapshot()

            # forward snapshot to sync engine
            if snapshot:
                self.sync_engine.bootstrap(snapshot)

        except Exception as e:
            print("[BINANCE ADAPTER] bootstrap error:", e)

    async def stop_user_stream(self):
        await self.stream.stop()

    # =====================================================
    # SNAPSHOT / MAPPING
    # =====================================================

    def get_snapshot(self):
        return self.sync.snapshot()

    def map_order(self, raw):
        return mapper.map_order(raw)

    def map_position(self, raw):
        return mapper.map_position(raw)

    def map_balance(self, raw):
        return mapper.map_balance(raw)

    # =====================================================
    # STEP 4 VIEW API
    # =====================================================

    def get_positions(self):
        snap = self.get_snapshot()
        raw_positions = snap.get("positions", [])

        views = []
        for p in raw_positions:
            try:
                size = float(p.get("positionAmt", 0))
                if abs(size) < 1e-8:
                    views.append(
                        ExchangePositionView(
                            symbol=p.get("symbol"),
                            side=None,
                            size=0
                        )
                    )
                    continue

                side = "LONG" if size > 0 else "SHORT"

                views.append(
                    ExchangePositionView(
                        symbol=p.get("symbol"),
                        side=side,
                        size=abs(size)
                    )
                )
            except Exception as e:
                print("[EXCHANGE VIEW] position parse error:", e)

        return views

    def get_open_orders(self):
        """
        Trả về danh sách open orders hiện tại từ REST snapshot.
        """
        snap = self.get_snapshot()
        return snap.get("open_orders", [])

    # =====================================================
    # PROTECTIVE ORDERS (exchange-managed SL / TP)
    # =====================================================

    async def place_stop_loss(
        self, symbol, side, quantity, stop_price, execution_id
    ):
        close_side = "SELL" if side == "LONG" else "BUY"

        self.trade.place_order(
            execution_id=execution_id,
            symbol=symbol,
            side=close_side,
            type="STOP_MARKET",
            stopPrice=float(stop_price),
            closePosition=True,   # ✅ bật close position
            workingType="CONTRACT_PRICE"
        )

    async def place_take_profit(
        self, symbol, side, quantity, tp_price, execution_id
    ):
        close_side = "SELL" if side == "LONG" else "BUY"

        self.trade.place_order(
            execution_id=execution_id,
            symbol=symbol,
            side=close_side,
            type="TAKE_PROFIT_MARKET",
            stopPrice=float(tp_price),
            closePosition=True,   # ✅ bật close position
            workingType="CONTRACT_PRICE"
        )

    async def _maybe_place_brackets(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        execution_id,
        *,
        metadata: Optional[dict] = None,
    ):
        if not execution_id or quantity <= 0:
            return
        if metadata is None:
            metadata = {}
            if self.execution_state is not None and hasattr(
                self.execution_state, "get_metadata"
            ):
                metadata = self.execution_state.get_metadata(execution_id)

        sl = metadata.get("sl")
        tp = metadata.get("tp")

        try:
            if sl:
                await self.place_stop_loss(
                    symbol, position_side, quantity, sl, execution_id
                )
            if tp:
                await self.place_take_profit(
                    symbol, position_side, quantity, tp, execution_id
                )
        except Exception as e:
            print("[BRACKET_ORDER_ERROR]", e)

    # =====================================================
    # ABSTRACT API IMPLEMENTATION (required by base class)
    # =====================================================

    async def open_position(self, symbol: str, side: str, quantity: float, execution_id=None):

        local_id = execution_id or str(time.time())

        print("ADAPTER LOCAL_ID:", local_id)

        # 🔥 SIGNAL
        signal_time = time.time()

        self.sync_engine.register_signal(
            symbol,
            local_id,
            signal_time,
            None
        )

        binance_side = "BUY" if side == "LONG" else "SELL"

        # 🔥 ORDER SENT
        order_sent_time = time.time()

        self.sync_engine.update_order_sent(
            symbol,
            local_id,
            order_sent_time
        )

        self._bracket_hook_suppressed = True
        try:
            response = self.trade.place_order(
                execution_id=local_id,
                newClientOrderId=local_id,
                symbol=symbol,
                side=binance_side,
                type="MARKET",
                quantity=quantity,
            )
        finally:
            self._bracket_hook_suppressed = False

        # 🔥 REAL BINANCE ID
        real_id = response.get("clientOrderId")

        print("REAL EXECUTION_ID:", real_id)

        # 🔥 migrate latency buffer
        if real_id and real_id != local_id:
            self.sync_engine.migrate_execution_id(
                symbol,
                local_id,
                real_id
            )

        filled_qty = float(response.get("executedQty", 0))
        status = response.get("status", "UNKNOWN")

        metadata = {}
        if self.execution_state is not None and hasattr(
            self.execution_state, "get_metadata"
        ):
            metadata = self.execution_state.get_metadata(local_id)

        sl = metadata.get("sl")
        tp = metadata.get("tp")

        if filled_qty > 0:
            if sl:
                try:
                    await self.place_stop_loss(
                        symbol, side, filled_qty, sl, local_id
                    )
                except Exception as e:
                    print("[BRACKET_SL_ERROR]", e)
            if tp:
                try:
                    await self.place_take_profit(
                        symbol, side, filled_qty, tp, local_id
                    )
                except Exception as e:
                    print("[BRACKET_TP_ERROR]", e)

        return FillResult(
            filled_quantity=filled_qty,
            status=status,
            raw=response
        )

    async def close_position(self, symbol: str, quantity: float, execution_id=None):

        local_id = execution_id or str(time.time())

        print("ADAPTER LOCAL_ID:", local_id)

        signal_time = time.time()

        self.sync_engine.register_signal(
            symbol,
            local_id,
            signal_time,
            None
        )

        positions = self.get_positions()

        for p in positions:
            if p.symbol == symbol:
 
                side = "SELL" if p.side == "LONG" else "BUY"

                order_sent_time = time.time()

                self.sync_engine.update_order_sent(
                    symbol,
                    local_id,
                    order_sent_time
                )
 
                response = self.trade.place_order(
                    execution_id=local_id,
                    newClientOrderId=local_id,
                    symbol=symbol,
                    side=side,
                    type="MARKET",
                    quantity=quantity,
                    reduceOnly=True,
                )

                real_id = response.get("clientOrderId")

                print("REAL EXECUTION_ID:", real_id)

                # 🔥 migrate latency
                if real_id and real_id != local_id:
                    self.sync_engine.migrate_execution_id(
                        symbol,
                        local_id,
                        real_id
                    )

                filled_qty = float(response.get("executedQty", 0))
                status = response.get("status", "UNKNOWN")

                return FillResult(
                    filled_quantity=filled_qty,
                    status=status,
                    raw=response
                )

    async def fetch_position(self, symbol: str):
        # 🔥 Lấy từ SyncEngine (authoritative WS state)
        positions = self.sync.position.get_all()

        for p in positions:
            if p.symbol == symbol:
                return p

        return None
        
    @property
    def exchange_name(self) -> str:
        return "binance"
