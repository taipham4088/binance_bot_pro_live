# execution/reconciliation/drift_detector.py

import time
from typing import List

from execution.reconciliation.report import DriftType


class DriftDetector:
    """
    DriftDetector chỉ trả lời một câu hỏi:
    'Có đang xảy ra hiện tượng lệch nào không?'
    """

    def __init__(self, sync_engine, exchange_adapter, stale_threshold: float = 5.0):
        self.sync_engine = sync_engine
        self.exchange = exchange_adapter
        self.stale_threshold = stale_threshold

    # =========================
    # MAIN
    # =========================

    def detect(self) -> List[DriftType]:
        drifts: List[DriftType] = []

        # --- 1. Stale / heartbeat drift ---
        if self._is_stale():
            drifts.append(DriftType.STALE_STATE)

        # --- 2. Position drift ---
        drifts.extend(self._detect_position_drift())

        # --- 3. Order drift (tạm tắt để debug) ---
        # drifts.extend(self._detect_order_drift())

        return drifts


    # =========================
    # CHECKS
    # =========================

    def _is_stale(self) -> bool:
        """
        Local truth không update trong X giây.
        """
        last = getattr(self.sync_engine, "last_update_ts", None)
        if not last:
            return False
        return (time.time() - last) > self.stale_threshold

    def _detect_position_drift(self) -> List[DriftType]:
        """
        So local position với exchange snapshot.
        """
        drifts: List[DriftType] = []

        try:
            local_positions = self.sync_engine.get_positions()
            exchange_positions = self.exchange.get_positions()
        except Exception as e:
            print("[DRIFT] position drift check failed:", e)
            drifts.append(DriftType.MISSING_EVENT)
            return drifts

        local_map = {p.symbol: p for p in local_positions}
        exch_map = {p.symbol: p for p in exchange_positions}

        # exchange có mà local không
        for sym in exch_map:
            if sym not in local_map:
                drifts.append(DriftType.GHOST_POSITION)

        # local có mà exchange không
        for sym in local_map:
            if sym not in exch_map:
                drifts.append(DriftType.PHANTOM_LOCAL_POSITION)

        # cả hai có nhưng khác hướng / size
        for sym in local_map:
            if sym in exch_map:
                lp = local_map[sym]
                ep = exch_map[sym]

                try:
                    if lp.side != ep.side:
                        drifts.append(DriftType.PARTIAL_REVERSE)
                    elif abs(lp.size - ep.size) > 1e-8:
                        drifts.append(DriftType.MINOR_NUMERIC_DRIFT)
                except Exception as e:
                    print("[DRIFT] corrupted local position object:", e)
                    drifts.append(DriftType.CORRUPTED_LOCAL_STATE)
        
        return drifts


    def _detect_order_drift(self) -> List[DriftType]:
        """
        So local open orders với exchange.
        """
        drifts: List[DriftType] = []

        try:
            local_orders = self.sync_engine.get_open_orders()
            exchange_orders = self.exchange.get_open_orders()
        except Exception:
            drifts.append(DriftType.MISSING_EVENT)
            return drifts

        local_ids = {o.id for o in local_orders}
        exch_ids = {o.id for o in exchange_orders}

        # exchange có order mà local không biết
        ghost = exch_ids - local_ids
        if ghost:
            drifts.append(DriftType.GHOST_ORDER)

        return drifts
