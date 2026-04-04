# backend/reconciliation/drift_detector.py

from typing import Dict, List, Tuple
import time


class DriftDetector:
    """
    LEVEL 3 – LIVE GRADE DRIFT DETECTOR

    - Compare only (symbol, side, size)
    - Size tolerance
    - Stabilization window
    - No full dict comparison
    """

    def __init__(
        self,
        session_id: str,
        size_tolerance: float = 0.00001,
        stabilization_window_ms: int = 1500,
    ):
        self.session_id = session_id
        self.size_tolerance = size_tolerance
        self.stabilization_window_ms = stabilization_window_ms

    # =========================================================
    # INTERNAL HELPERS
    # =========================================================

    def _normalize_positions(self, positions: List[Dict]) -> Dict[Tuple[str, str], float]:
        """
        Convert positions list to:
        {
            (symbol, side): size
        }
        """
        normalized = {}

        for p in positions or []:
            symbol = p.get("symbol")
            side = p.get("side")
            size = float(p.get("size", 0))

            if not symbol or not side:
                continue

            normalized[(symbol, side)] = size

        return normalized

    # =========================================================
    # MAIN COMPARE
    # =========================================================

    def compare(self, paper: Dict, live: Dict) -> Dict:
        ts = int(time.time() * 1000)

        if not paper or not live:
            return {
                "status": "PENDING",
                "reason": "missing_execution_snapshot",
                "paper": bool(paper),
                "live_shadow": bool(live),
                "ts": ts,
            }

        paper_ts = paper.get("ts")
        live_ts = live.get("ts")

        # =========================
        # 1️⃣ Stabilization check
        # =========================
        if paper_ts and live_ts:
            if abs(paper_ts - live_ts) > self.stabilization_window_ms:
                # Not stable yet → do not detect drift
                return {
                    "status": "OK",
                    "diff": {},
                    "reason": "stabilizing_execution_window",
                    "paper_ts": paper_ts,
                    "live_ts": live_ts,
                    "checked_at": ts,
                }

        diff = {}

        # =========================
        # 2️⃣ Normalize positions
        # =========================
        paper_pos = self._normalize_positions(paper.get("positions", []))
        live_pos = self._normalize_positions(live.get("positions", []))

        all_keys = set(paper_pos.keys()) | set(live_pos.keys())

        position_drift = []

        for key in all_keys:
            paper_size = paper_pos.get(key, 0.0)
            live_size = live_pos.get(key, 0.0)

            if abs(paper_size - live_size) > self.size_tolerance:
                position_drift.append({
                    "symbol": key[0],
                    "side": key[1],
                    "paper_size": paper_size,
                    "live_size": live_size,
                })

        if position_drift:
            diff["positions"] = position_drift

        # =========================
        # 3️⃣ Active orders count drift
        # (optional – lightweight check)
        # =========================
        
        status = "DRIFT" if diff else "OK"

        return {
            "status": status,
            "diff": diff,
            "paper_ts": paper_ts,
            "live_ts": live_ts,
            "checked_at": ts,
        }
