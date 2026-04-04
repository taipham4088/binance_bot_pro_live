# backend/reconciliation/reconciliation_hub.py

from backend.controlled_reaction.decision_engine import Phase45DecisionEngine
from backend.controlled_reaction.reaction_contract import SeverityLevel
from backend.reconciliation.invariant_engine import InvariantEngine
from backend.reconciliation.drift_detector import DriftDetector
import time
from typing import Optional, Dict
import asyncio


class ReconciliationHub:
    """
    SYSTEM-LEVEL RECONCILIATION HUB

    Phase 4.4
    - Collect execution snapshots from paper & live_shadow
    - Perform real drift diff (pairwise)
    - Detect invariant violations & severity

    Phase 4.5
    - Emit controlled reaction (signal-only)
    - Persist reaction into state_hub
    """

    # ==================================================
    # Severity mapping (Phase 4.4 -> Phase 4.5)
    # ==================================================
    @staticmethod
    def map_severity_to_phase45(severity: str) -> SeverityLevel:
        """
        Default-safe mapping.
        Unknown severity => INFO
        """
        mapping = {
            "OK": SeverityLevel.INFO,
            "WARN": SeverityLevel.WARN,
            "ERROR": SeverityLevel.ERROR,
            "CRITICAL": SeverityLevel.CRITICAL,
        }
        return mapping.get(severity, SeverityLevel.INFO)

    # ==================================================
    # INIT
    # ==================================================
    def __init__(self, session_id: str, mode: str, state_hub):
        self.session_id = session_id
        self.mode = mode
        self.state_hub = state_hub   # 👈 Phase 4.5 persistence target

        # execution snapshots
        self.paper_exec: Optional[Dict] = None
        self.live_exec: Optional[Dict] = None

        # drift engine
        self.drift = DriftDetector(session_id=session_id)

        # Phase 4.4.3 – invariant & severity
        self.invariant = InvariantEngine()
        # ==============================
        # Level 3 Drift Stability Config
        # ==============================
        self.drift_config = {
            "min_consecutive": 3,
            "min_age_ms": 300,
            "require_idle": True,
            "require_no_active_orders": True,
        }

        self._drift_state = {
            "last_signature": None,
            "first_seen_at": None,
            "count": 0,
        }

    def _make_signature(self, diff_dict: Dict) -> str:
        """
        Create stable signature for diff comparison.
        """
        return str(sorted(diff_dict.items()))

    # ==================================================
    # INPUT – FEED EXECUTION SNAPSHOT
    # ==================================================
    def update_execution(self, *, mode: str, execution_event: Dict):
        """
        Called by WS / pipeline after execution is emitted.
        Stores snapshot only – NO LOGIC.
        """
        if not execution_event:
            return

        if mode == "paper":
            self.paper_exec = execution_event
        elif mode == "live_shadow":
            self.live_exec = execution_event

    # ==================================================
    # DRIFT + INVARIANT + CONTROLLED REACTION
    # ==================================================
    def detect(self) -> dict:
        ts = int(time.time() * 1000)

        # ---------- NOT READY ----------
        if not self.paper_exec or not self.live_exec:
            return {
                "status": "PENDING",
                "severity": "OK",
                "reason": "waiting_for_both_sessions",
                "paper_ready": self.paper_exec is not None,
                "live_shadow_ready": self.live_exec is not None,
                "ts": ts,
            }

        # ---------- PHASE 4.4 ----------
        diff = self.drift.compare(self.paper_exec, self.live_exec)
        violations = self.invariant.check(self.paper_exec, self.live_exec)
        raw_diff = diff.get("diff", {})

        # =====================================
        # Level 3 – Stability Gate
        # =====================================

        # 1️⃣ Require no active orders
        if self.drift_config["require_no_active_orders"]:
            if self.paper_exec.get("activeOrders") or self.live_exec.get("activeOrders"):
                return {
                    "status": "SETTLING",
                    "severity": "OK",
                    "reason": "active_orders_pending",
                    "paper_ts": self.paper_exec.get("ts"),
                    "live_ts": self.live_exec.get("ts"),
                    "checked_at": ts,
                }

        # 2️⃣ If no diff → reset memory
        if not raw_diff:
            self._drift_state = {
                "last_signature": None,
                "first_seen_at": None,
                "count": 0,
            }
            diff["status"] = "OK"
        else:
            signature = self._make_signature(raw_diff)

            if signature == self._drift_state["last_signature"]:
                self._drift_state["count"] += 1
            else:
                self._drift_state = {
                    "last_signature": signature,
                    "first_seen_at": ts,
                    "count": 1,
                }

            age = ts - self._drift_state["first_seen_at"]
    
            if (
                self._drift_state["count"] < self.drift_config["min_consecutive"]
                or age < self.drift_config["min_age_ms"]
            ):
                diff["status"] = "STABILIZING"
            else:
                diff["status"] = "DRIFT"

        
        severity = "OK"

        if violations:
            severity = max(v["severity"] for v in violations)

        elif diff.get("status") == "DRIFT":
            severity = "WARN"


        # ---------- PHASE 4.5 ----------
        phase45_severity = self.map_severity_to_phase45(severity)

        reaction_decision = Phase45DecisionEngine.decide(
            reconciliation_id=self.session_id,
            severity=phase45_severity,
            invariant_violations=violations,
        )

        # 🔐 Persist reaction (signal-only)
        asyncio.create_task(
            self.state_hub.record_reaction(reaction_decision)
        )

        # ---------- RETURN SNAPSHOT ----------
        return {
            "status": diff.get("status", "OK"),
            "severity": severity,
            "diff": diff,
            "invariants": violations,
            "reaction": reaction_decision,   # for inspection / WS
            "paper_ts": self.paper_exec.get("ts"),
            "live_ts": self.live_exec.get("ts"),
            "checked_at": ts,
        }
