# backend/core/system_state_engine.py
from backend.analytics.trade_journal import TradeJournal
from backend.core.system_state_contract import new_delta, deep_clone
from backend.core.system_state_builder import SystemStateBuilder
import time
from datetime import datetime
import asyncio
import copy
import inspect



class SystemStateEngine:
    """
    App Brain.
    Gom toàn bộ state hệ thống thành 1 snapshot chuẩn cho dashboard.
    """

    def __init__(self, session, state_hub=None):
        self.trade_journal = TradeJournal(
            mode=session.id,
            logical_mode=getattr(session, "api_mode", session.mode),
        )
        self.builder = SystemStateBuilder(session_id=session.id)
        self.session = session
        self.state_hub = state_hub

        self.seq = 0

        self.state = {
            "system": {},
            "account": {},                       
            "risk": {},
            "execution": {},
            "analytics": {},
            "health": {},
            "reconciliation": {}   # 👈 PHASE 4.3
        }

        self.execution_state = None
        self.account = None
        
        self._last_sent = {}          # cache last sent blocks
        self._delta_enabled = True   # flag (sau này dễ tắt/mở)
        self._heartbeat_interval = 1.0   # seconds
        self._heartbeat_task = None
        self._alive = True
        # ===== Health hysteresis guard =====
        self._bad_health_ticks = 0
        self._good_health_ticks = 0
        self._health_level = "OK"
        # Measured exchange ack latency (order ack - order sent), ms; EMA for grace.
        self._exchange_latency_ms = None
        self._latency_ema_alpha = 0.25
        self._latency_fallback_ms = 1500
        self._max_latency_sample_ms = 60000

    def _intent_order_sent_ms(self, intent, default_ms: int) -> int:
        """Best available order_sent_time (ms); pipeline may set attrs on intent."""
        for name in ("exchange_order_sent_time", "order_sent_time", "orderSentTime"):
            v = getattr(intent, name, None)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        v = getattr(intent, "ts", None)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
        return int(default_ms)

    def _record_exchange_latency_ms(self, sample_ms: int) -> None:
        if sample_ms < 0 or sample_ms > self._max_latency_sample_ms:
            return
        if self._exchange_latency_ms is None:
            self._exchange_latency_ms = float(sample_ms)
        else:
            a = self._latency_ema_alpha
            self._exchange_latency_ms = a * sample_ms + (1.0 - a) * self._exchange_latency_ms

    def _grace_ms_position_missing(self) -> int:
        """
        Grace before POSITION_MISSING_AFTER_SUBMIT:
        min(max(500, latency * 2), 3000) with latency from EMA; else fallback 1500.
        """
        lat = self._exchange_latency_ms
        if lat is None:
            return self._latency_fallback_ms
        li = int(round(lat))
        return min(max(500, li * 2), 3000)

    def on_intent_submitted(self, intent):
        self.state.setdefault("execution", {})

        now = int(time.time() * 1000)
        order_sent_ms = self._intent_order_sent_ms(intent, now)
        active_intent = {
            "intentId": getattr(intent, "intent_id", None),
            "symbol": getattr(intent, "symbol", None),
            "side": getattr(intent, "side", None),
            "size": getattr(intent, "qty", None),
            "source": getattr(intent, "source", None),
            "status": "OPEN",
            "submittedAt": now,
            "intentSubmitTime": now,
            "orderSentTime": order_sent_ms,
        }

        self.state["execution"]["activeIntent"] = active_intent
        self.state["execution"]["lastIntent"] = dict(active_intent)
        self.state["execution"]["intentId"] = active_intent["intentId"]
        self.state["execution"]["intentStatus"] = "OPEN"

        self.emit_delta("execution", self.state["execution"])


    def on_market_mode(self, market_state):
        """
        market_state: MarketModeState
        """
        analytics = self.state["analytics"]

        analytics["regime"] = market_state.mode.value
        analytics["side_bias"] = market_state.side_bias
        analytics["confidence"] = market_state.confidence
        analytics["last_update"] = market_state.ts

        self.emit_delta("analytics", analytics)

    # =====================================================
    # BOOTSTRAP
    # =====================================================

    def bind(self):
        now = int(time.time() * 1000)

        # ===== STEP 1: SYSTEM CORE =====
        self.state["system"] = {
            "status": "RUNNING",
            "authority": self.session.mode.upper(),  # paper -> PAPER
            "started_at": now,
            "uptimeSec": 0
        }
        
        # execution state
        if hasattr(self.session.engine, "execution_state"):
            self.execution_state = self.session.engine.execution_state
            # 🔥 bind execution state change listener
            if self.execution_state:
                self.execution_state.on_change = self._on_execution_state_change

        # account adapter
        self.account = getattr(self.session.engine, "account", None)

        # risk events
        if self.session.risk_system and hasattr(self.session.risk_system, "subscribe"):
            self.session.risk_system.subscribe(self.on_risk_event)

        # market mode (analytics)
        if hasattr(self.session, "market_mode_engine"):
            self.session.market_mode_engine.subscribe(self.on_market_mode)

        # ---- analytics: session-scoped bus routing + restore resolver ----
        try:
            from backend.analytics.session_publish_context import (
                register_sync_engine_session,
                register_stub_execution_session,
            )
            from backend.observability.session_journal_registry import (
                register_trade_journal,
            )

            register_trade_journal(self.session.id, self.trade_journal)

            ls = getattr(self.session, "live_system", None)
            eng = getattr(self.session, "engine", None)

            if ls and getattr(ls, "sync_engine", None):
                se = ls.sync_engine
                register_sync_engine_session(se, self.session.id)

                def _journal_restore_resolver(symbol: str):
                    if not getattr(se, "_bootstrapped", False):
                        return None
                    min_sz = se._get_symbol_min_size(symbol)
                    for p in se.position.get_all():
                        if p.symbol == symbol:
                            sz = abs(float(p.size))
                            if sz > min_sz * 0.5:
                                return {"side": p.side, "size": sz}
                            return False
                    return False

                self.trade_journal.set_exchange_position_resolver(
                    _journal_restore_resolver
                )
            elif eng is not None and type(eng).__name__ == "StubExecution":
                register_stub_execution_session(eng, self.session.id)
        except Exception as e:
            print("[STATE_ENGINE] session analytics bridge:", e)

    # =====================================================

    def start_heartbeat(self):
        if self._heartbeat_task is None:
            print("[STATE_ENGINE] start heartbeat")
            asyncio.create_task(self._heartbeat_loop())
                 
    # =====================================================
    # REFRESH ALL
    # =====================================================

    def refresh_all(self):
        """
        Rebuild full system snapshot from engines.
        """
        # 🔥 FORCE REFRESH EXECUTION STATE
        self._refresh_execution()
        
        system_state = {
            "state": self.session.status,     # đổi status -> state
            "mode": self.session.mode,
            "last_event": "REFRESH_ALL"
        }
        
        snapshot = self.builder.refresh_all(
            system=system_state
        )

        # 🔥 FORCE overwrite state từ session runtime
        snapshot["system"]["state"] = self.session.status or "RUNNING"
        snapshot["system"]["mode"] = self.session.mode or "shadow"
        snapshot["system"]["last_event"] = "REFRESH_ALL"
        
        # 🔥 PRESERVE reconciliation state
        if "reconciliation" in self.state:
            snapshot["reconciliation"] = self.state.get("reconciliation", {})

        # 🔥 PRESERVE execution state (VERY IMPORTANT)
        snapshot["execution"] = self.state.get("execution", {})

        self.state = snapshot
        return snapshot
    # =====================================================
    # EMIT TO DASHBOARD
    # =====================================================

    async def emit_snapshot(self):
        print("==== EMIT_SNAPSHOT CALLED ====")
        print("SESSION ID:", self.session.id)
        print("SESSION STATUS:", self.session.status)
        if self.session.status != "RUNNING":
            return   # ❗không snapshot sớm

        # 🔥 ENSURE execution block is fresh
        self._refresh_execution()
        # =========================
        # BUILD RAW SNAPSHOT
        # =========================
        snapshot = self.refresh_all()
        # 🔒 ENSURE reconciliation is not lost
        snapshot["reconciliation"] = self.state.get("reconciliation", {})

        # =========================
        # NORMALIZE SYSTEM STATE v1
        # =========================

        # --- risk ---
        raw_risk = snapshot.get("risk") or {}
        snapshot["risk"] = {
            "state": "FROZEN" if raw_risk.get("isFrozen") else "OK",
            "violations": raw_risk.get("violations", []),
            "limits": raw_risk.get("limits", {}),
        }

        # --- execution ---
        exec_block = snapshot.get("execution") or {}

        snapshot["execution"] = {
            "status": exec_block.get("status"),
            "reason": exec_block.get("reason"),
            "since": exec_block.get("since"),
            "uptime": exec_block.get("uptime"),

            "positions": exec_block.get("positions", []),
            "activeOrders": exec_block.get("activeOrders", []),
            "lastAction": exec_block.get("lastAction"),
        }

        # --- health ---
        health_components = {}
        health_level = "OK"

        # 1. Risk dominates
        if snapshot["risk"]["state"] in ("FROZEN", "BLOCKED"):
            health_components["risk"] = "DOWN"
            health_level = "CRITICAL"
        else:
            health_components["risk"] = "OK"

        # 2. Execution
        if snapshot["execution"]["activeOrders"] and snapshot["execution"]["lastAction"] is None:
            health_components["execution"] = "DEGRADED"
            if health_level != "CRITICAL":
                health_level = "WARN"
        else:
            health_components["execution"] = "OK"

        # 3. Account
        if not snapshot.get("account"):
            health_components["account"] = "DEGRADED"
            if health_level == "OK":
                health_level = "WARN"
        else:
            health_components["account"] = "OK"

        snapshot["health"] = {
            "level": health_level,
            "components": health_components,
        }

        # =========================
        # EMIT VIA STATE HUB
        # =========================
        # 🔒 ENSURE system is always present in snapshot
        snapshot.setdefault("system", {})
        snapshot["system"]["state"] = self.session.status or "RUNNING"
        snapshot["system"]["mode"] = self.session.mode or "shadow"
        
        self.seq += 1
        print("==== SNAPSHOT SYSTEM BLOCK ====")
        print(snapshot.get("system"))

        await self.state_hub.emit_snapshot(
            self.session.id,
            snapshot
        )
                    
    # =====================================================

    def emit_delta(self, block_name: str, block_value: dict):
        
        if not self._delta_enabled:
            return

        if not self._block_changed(block_name, block_value):
            return

        # 👇 PHASE 4.4.3 – persist reconciliation into snapshot memory
        if block_name == "reconciliation":
            self.state["reconciliation"] = block_value   
        # =========================
        # ✅ SEMANTIC LOGGING
        # =========================
        if block_name == "system":
            prev = self._last_sent.get("system")
            curr = self._semantic_system_view(block_value)

            prev_sem = self._semantic_system_view(prev) if prev else None

            if curr != prev_sem:
                print(
                    "[STATE][CHANGE]",
                    f"session={self.session.id}",
                    "block=system",
                    f"value={curr}",
                )

        elif block_name in ("risk", "execution", "reconciliation"):

            prev = self._last_sent.get(block_name)
            prev_sem = prev if prev else None
            curr_sem = block_value

            if curr_sem != prev_sem:
                print(
                    "[STATE][CHANGE]",
                    f"session={self.session.id}",
                    f"block={block_name}",
                    f"value={block_value}",
                )

        # ---- Phase 4.5: mirror execution snapshot to SYSTEM reconciliation ----
        if block_name == "execution":
            if self.session.app and hasattr(self.session.app.state, "manager"):
                system_recon = self.session.app.state.manager.reconciliation_hub
                system_recon.update_execution(
                    mode=self.session.mode,
                    execution_event=block_value  # 👈 DÙNG DATA THẬT
                )
        # =========================

        self.seq += 1

        delta = new_delta(
            self.session.id,
            {block_name: block_value},
            seq=self.seq,
            ts=int(time.time() * 1000)
        )

        self._last_sent[block_name] = deep_clone(block_value)

        asyncio.create_task(
            self.state_hub.emit_delta(
                self.session.id,
                delta
            )
        )

    
    # =====================================================
    # SYSTEM
    # =====================================================
    
    def _refresh_system(self):
        now = int(time.time() * 1000)

        self.builder.state["system"].update({
            "state": self.session.status,
            "mode": self.session.mode,
            "last_event": "SYSTEM_REFRESH"
        })

        start = self.builder.state["system"].get("started_at")
        if start:
            self.builder.state["system"]["uptime"] = now - start

    # =====================================================
    # EXECUTION
    # =====================================================

    def _refresh_execution(self):

        if self.execution_state:
            prev_execution = self.state.get("execution", {})
            self.state["execution"] = {
                **prev_execution,
                **self.execution_state.snapshot(),
            }
            self.state["execution_state"] = self.execution_state.status.value

            live_system = getattr(self.session, "live_system", None)

            if live_system:
                sync_engine = getattr(live_system, "sync_engine", None)
            else:
                sync_engine = None

            if sync_engine:
                try:
                    positions = sync_engine.position.get_all()

                    # ===== PRIMARY SOURCE =====
                    if positions:
                        prev_positions = {
                            p["symbol"]: p
                            for p in self.state["execution"].get("positions", [])
                        }

                        new_positions = []

                        for p in positions:
                            prev = prev_positions.get(p.symbol, {})

                            entry_price = getattr(p, "entry_price", None)
                            if entry_price is None:
                                entry_price = prev.get("entry_price")

                            unrealized = getattr(p, "unrealized_pnl", None)
                            if unrealized is None:
                                unrealized = prev.get("unrealized_pnl", 0.0)

                            new_positions.append({
                                "symbol": p.symbol,
                                "side": p.side,
                                "size": p.size,
                                "entry_price": entry_price,
                                "unrealized_pnl": unrealized,
                            })

                        self.state["execution"]["positions"] = new_positions

                    # ===== FALLBACK (restart safe) =====
                    else:
                        snapshot = self.execution_state.snapshot()
                        fallback = snapshot.get("positions", [])

                        self.state["execution"]["positions"] = fallback

                except Exception as e:
                    print("POSITION REFRESH ERROR:", e)
                    self.state["execution"]["positions"] = []

            else:
                print("SYNC ENGINE NOT FOUND")
                self.state["execution"]["positions"] = []

        try:
            self.trade_journal._resolve_pending_restore()
        except Exception:
            pass

        self._reconcile_intent_state()
    # =====================================================
    # EXECUTION DECISION (PHASE 3.4)
    # =====================================================

    def on_execution_event(self, event):
        """
        Receive execution decision and update position state (multi-symbol)
        """

        self.state.setdefault("execution", {})
        self.state["execution"].setdefault("positions", [])

        positions = self.state["execution"]["positions"]
        current_active_intent = self.state["execution"].get("activeIntent")

        # -------------------------------------------------
        # OPENED → add/update position
        # -------------------------------------------------
        if event.decision == "OPENED":
            symbol = event.symbol
            side = event.side
            size = event.size

            # Remove existing position for same symbol
            positions = [p for p in positions if p["symbol"] != symbol]

            positions.append({
                "symbol": symbol,
                "side": side,
                "size": size
            })
            # ---- analytics journal ----
            self.trade_journal.on_position_open(
                symbol=symbol,
                side=(side or "").upper(),
                price=0,
                size=size
            )

            self.state["execution"]["positions"] = positions
            # optional: vẫn giữ pending cho UI/debug
            self.state["execution"]["pendingSymbol"] = symbol
            self.state["execution"]["pendingSide"] = side
            self.state["execution"]["pendingSize"] = size

            # Latency sample: exchange_ack_time (event.ts) - order_sent_time
            if current_active_intent and event.ts is not None:
                sent = current_active_intent.get("orderSentTime")
                if sent is not None:
                    lat = int(event.ts) - int(sent)
                    if lat >= 0:
                        self._record_exchange_latency_ms(lat)

        # -------------------------------------------------
        # CLOSED → remove position by symbol
        # -------------------------------------------------
        elif event.decision == "CLOSED":
            symbol = event.symbol
            size = event.size

            # ---- analytics journal ----
            self.trade_journal.on_position_close(
                price=0,
                size=size
            )

            positions = [p for p in positions if p["symbol"] != symbol]
            self.state["execution"]["positions"] = positions

            # clear pending
            self.state["execution"]["pendingSymbol"] = symbol
            self.state["execution"]["pendingSide"] = None
            self.state["execution"]["pendingSize"] = None

        intent_status = None
        if event.reason == "EXECUTION_COMPLETED":
            intent_status = "COMPLETED"
        elif event.decision == "REFUSED":
            intent_status = "REJECTED"
        elif event.decision == "CLOSED":
            intent_status = "CLOSED"

        if intent_status and current_active_intent:
            completed_intent = dict(current_active_intent)
            completed_intent["status"] = intent_status
            completed_intent["resolvedAt"] = event.ts
            completed_intent["resolutionReason"] = event.reason
            self.state["execution"]["lastIntent"] = completed_intent
            self.state["execution"]["activeIntent"] = None
            self.state["execution"]["intentStatus"] = intent_status

        # -------------------------------------------------
        # Update metadata
        # -------------------------------------------------
        self.state["execution"].update({
            "lastDecision": event.decision,
            "reason": event.reason,
            "intentId": event.intent_id,
            "ts": event.ts,
        })

        self.emit_delta("execution", self.state["execution"])

        if event.decision in ("OPENED", "CLOSED"):
            try:
                sess = getattr(self, "session", None)
                if sess is not None and hasattr(
                    sess, "on_execution_decision_for_daily_risk"
                ):
                    sess.on_execution_decision_for_daily_risk(event.decision)
            except Exception:
                pass

    def _reconcile_intent_state(self):
        execution = self.state.setdefault("execution", {})
        active_intent = execution.get("activeIntent")

        if not active_intent:
            return

        symbol = active_intent.get("symbol")
        side = str(active_intent.get("side") or "").upper()
        positions = execution.get("positions", [])

        matching_position = None
        for pos in positions:
            if pos.get("symbol") == symbol:
                matching_position = pos
                break

        if matching_position is None:
            t0 = active_intent.get("orderSentTime")
            if t0 is None:
                t0 = active_intent.get("intentSubmitTime")
            if t0 is None:
                t0 = active_intent.get("submittedAt")
            if t0 is not None:
                elapsed_ms = int(time.time() * 1000) - int(t0)
                grace_ms = self._grace_ms_position_missing()
                if elapsed_ms < grace_ms:
                    return
            resolved_intent = dict(active_intent)
            resolved_intent["status"] = "INVALIDATED"
            resolved_intent["resolvedAt"] = int(time.time() * 1000)
            resolved_intent["resolutionReason"] = "POSITION_MISSING_AFTER_SUBMIT"
            execution["lastIntent"] = resolved_intent
            execution["activeIntent"] = None
            execution["intentStatus"] = "INVALIDATED"
            execution["pendingSymbol"] = None
            execution["pendingSide"] = None
            execution["pendingSize"] = None
            execution["lastDecision"] = "INVALIDATED"
            execution["reason"] = "POSITION_MISSING_AFTER_SUBMIT"
            return

        actual_side = str(matching_position.get("side") or "").upper()

        if side and actual_side and side != actual_side:
            resolved_intent = dict(active_intent)
            resolved_intent["status"] = "INVALIDATED"
            resolved_intent["resolvedAt"] = int(time.time() * 1000)
            resolved_intent["resolutionReason"] = "POSITION_SIDE_DIVERGED"
            execution["lastIntent"] = resolved_intent
            execution["activeIntent"] = None
            execution["intentStatus"] = "INVALIDATED"
            execution["pendingSymbol"] = None
            execution["pendingSide"] = None
            execution["pendingSize"] = None
            execution["lastDecision"] = "INVALIDATED"
            execution["reason"] = "POSITION_SIDE_DIVERGED"
        # =========================
        # 🔥 SIZE DIVERGED (NEW FIX)
        # =========================
        intent_size = float(active_intent.get("size") or 0)
        actual_size = float(matching_position.get("size") or 0)

        if intent_size and actual_size and actual_size != intent_size:
            resolved_intent = dict(active_intent)
            resolved_intent["status"] = "INVALIDATED"
            resolved_intent["resolvedAt"] = int(time.time() * 1000)
            resolved_intent["resolutionReason"] = "POSITION_SIZE_DIVERGED"

            execution["lastIntent"] = resolved_intent
            execution["activeIntent"] = None
            execution["intentStatus"] = "INVALIDATED"

            execution["pendingSymbol"] = None
            execution["pendingSide"] = None
            execution["pendingSize"] = None

            execution["lastDecision"] = "INVALIDATED"
            execution["reason"] = "POSITION_SIZE_DIVERGED"

            return

    # =====================================================
    # ACCOUNT
    # =====================================================

    def _refresh_account(self):
        if not self.account:
            return

        self.state["account"] = {
            "balance": self.account.get_balance(),
            "equity": self.account.get_equity(),
            "last_update": time.time()
        }

    # =====================================================
    # POSITIONS
    # =====================================================

    def _refresh_positions(self):
        try:
            if hasattr(self.session.engine, "sync_engine"):
                pos_engine = self.session.engine.sync_engine.position
                positions = pos_engine.get_all()
                self.state["positions"] = [p.__dict__ for p in positions]
        except Exception as e:
            print("[SystemStateEngine] position refresh error:", e)

    # =====================================================
    # RISK
    # =====================================================

    def on_risk_event(self, event: dict):
        self._refresh_risk()
        self.emit_delta("risk", self.state["risk"])

    def _refresh_risk(self):
        if self.session.risk_system and hasattr(self.session.risk_system, "snapshot"):
            self.state["risk"] = self.session.risk_system.snapshot()

    
    # =====================================================
    # HEALTH
    # =====================================================

    def _refresh_health(self):
        if hasattr(self.session, "health_check"):
            self.state["health"] = self.session.health_check()
    # =====================================================
    # SEMANTIC HELPERS
    # =====================================================

    def _semantic_system_view(self, system_block: dict) -> dict:
        """
        Extract only meaningful system state fields.
        Ignore heartbeat / uptime / timestamps.
        """
        if not system_block:
            return {}

        return {
            "state": system_block.get("state"),
            "mode": system_block.get("mode"),
            "last_event": system_block.get("last_event"),
            "last_error": system_block.get("last_error"),
        }

    # =====================================================       
    def _block_changed(self, name: str, block: dict) -> bool:
        last = self._last_sent.get(name)

        if last is None:
            return True

        # ===== Special handling for execution block =====
        if name == "execution":

            def normalize(b):
                if not isinstance(b, dict):
                    return b

                return {
                    k: v
                    for k, v in b.items()
                    if k not in ("uptime", "since")
                }

            return normalize(last) != normalize(block)

        return last != block

    # =====================================================   

    async def _heartbeat_loop(self):
        while self._alive:
            await asyncio.sleep(self._heartbeat_interval)
            self._on_heartbeat()

    # =====================================================   
    def _on_heartbeat(self):
        #===========================================
        # sẽ xóa sau khi kiểm tra xong position
        engine = getattr(self.session.engine, "sync_engine", None)

        if engine:
            current = engine.position.positions

            if getattr(self, "_last_pos", None) != current:
                print("=== RUNTIME POSITION MEMORY ===")
                print(current)
                print("================================")
                self._last_pos = current
        #===========================================

        now = int(time.time() * 1000)

       # ===== SYSTEM =====
        started_at = self.state["system"].get("started_at")
        if started_at:
            self.state["system"]["uptimeSec"] = (now - started_at) // 1000

        # ===== HEALTH COMPONENTS =====
        components = {}

        # 1. State engine (luôn OK nếu heartbeat chạy)
        components["state_engine"] = "OK"

        # 2. Risk system
        risk_state = self.state.get("risk", {}).get("state")
        if risk_state in ("FROZEN", "BLOCKED"):
            components["risk"] = "DOWN"
        elif risk_state:
            components["risk"] = "OK"
        else:
            components["risk"] = "UNKNOWN"

        # 3. Execution
        exec_state = self.state.get("execution", {})
        if exec_state.get("activeOrders") and exec_state.get("lastAction") is None:
            components["execution"] = "DEGRADED"
        else:
            components["execution"] = "OK"

        # 4. Exchange (chưa implement health check → UNKNOWN)
        components["exchange_ws"] = "UNKNOWN"
        components["exchange_rest"] = "UNKNOWN"

        # ===== OVERALL LEVEL =====
        if "DOWN" in components.values():
            level = "CRITICAL"
        elif "DEGRADED" in components.values():
            level = "WARN"
        else:
            level = "OK"
        # ===== Hysteresis guard =====
        raw_level = level

        if raw_level in ("CRITICAL", "WARN"):
            self._bad_health_ticks += 1
            self._good_health_ticks = 0
        else:
            self._good_health_ticks += 1
            self._bad_health_ticks = 0

        # degrade only after 2 consecutive bad ticks
        if self._bad_health_ticks >= 2:
            self._health_level = raw_level

        # recover only after 2 consecutive good ticks
        if self._good_health_ticks >= 2:
            self._health_level = "OK"

        level = self._health_level    

        self.state["health"] = {
            "level": level,
            "components": components,
        }

        # ===== EMIT DELTA =====
        self.emit_delta("system", self.state["system"])
        # Ensure execution positions reflect latest SyncEngine state
        # Refresh execution snapshot
        old_exec = self.state.get("execution", {}).copy()

        self._refresh_execution()

        new_exec = self.state.get("execution", {})

        # Emit only if execution block changed
        if old_exec != new_exec:
            self.emit_delta("execution", new_exec)
        self.emit_delta("health", self.state["health"])
    

        # ===================================================== 
    def stop(self):
        self._alive = False

    # =====================================================
    # CORE STATE EXTRACTORS (for Orchestrator)
    # =====================================================

    def get_position_state(self):
        positions = self.state.get("execution", {}).get("positions", [])
        if not positions:
            return {"side": "flat", "size": 0}

        # single-symbol version trước
        p = positions[0]
        return {
            "side": p.get("side", "flat").lower(),
            "size": p.get("size", 0)
        }


    def get_risk_state(self):
        risk = self.state.get("risk", {})
        return {
            "breach": risk.get("state") in ("BLOCKED", "FROZEN"),
            "kill_switch": risk.get("state") == "FROZEN"
        }


    def get_health_state(self):
        health = self.state.get("health", {})
        level = health.get("level", "OK")

        if level == "CRITICAL":
            return "critical"
        if level == "WARN":
            return "degraded"
        return "normal"

    # =====================================================
    # EXECUTION STATE LISTENER (Phase 3 Fix)
    # =====================================================
    def _on_execution_state_change(self, exec_state):
        """
        Called whenever ExecutionState changes.
        Only emit when status actually changes.
        """

        old_status = self.state.get("execution", {}).get("status")

        self._refresh_execution()

        new_status = self.state.get("execution", {}).get("status")

        if old_status != new_status:
            self.emit_delta("execution", self.state["execution"])




  

    
