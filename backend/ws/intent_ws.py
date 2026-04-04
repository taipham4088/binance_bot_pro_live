import asyncio
from trading_core.execution_policy.intent_schema import ExecutionIntent, IntentType
from backend.core.run_manager import RunManager
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from uuid import uuid4
import json

router = APIRouter()


@router.websocket("/ws/intent/{session_id}")
async def ws_intent(websocket: WebSocket, session_id: str):

    await websocket.accept()
    print("[INTENT_WS] connect:", session_id)

    while True:
        try:

            # =========================
            # RECEIVE MESSAGE
            # =========================
            frame = await websocket.receive_text()
            raw_msg = json.loads(frame)

            intent_id = raw_msg.get("intent_id") or str(uuid4())
            payload = raw_msg.get("payload", {})

            manager: RunManager = websocket.app.state.manager
            session = manager.sessions.get(session_id)

            if not session:
                print("[INTENT][DROP] session not found:", session_id)
                continue


            # =========================
            # READ CURRENT POSITION
            # =========================
            exec_state = session.system_state.state.get("execution", {})
            positions = exec_state.get("positions", [])

            if positions:
                pos = positions[0]
                metadata = {
                    "position_side": pos.get("side"),
                    "position_size": pos.get("size")
                }
            else:
                metadata = {
                    "position_side": "flat",
                    "position_size": 0
                }


            # =========================
            # BUILD EXECUTION INTENT
            # =========================
            metadata["price"] = payload.get("price")

            exec_intent = ExecutionIntent(
                intent_id=intent_id,
                symbol=payload.get("symbol"),
                type=IntentType(raw_msg.get("type")),
                side=payload.get("side"),
                qty=payload.get("qty"),
                source=raw_msg.get("source", "manual"),
                metadata=metadata
            )

            exec_intent.validate_schema()

            # =========================
            # IDEMPOTENCY GUARD
            # =========================
            if exec_intent.intent_id in session.processed_intents:
                print("[IDEMPOTENCY][BLOCK]", exec_intent.intent_id)
                continue

            session.processed_intents.add(exec_intent.intent_id)


            # =========================
            # EXECUTION
            # =========================
            event = None

            async with session.execution_lock:
                event = await session.inject_intent(exec_intent)


            # =========================
            # RISK EVALUATION
            # =========================
            if session.risk_system:

                risk_state = session.risk_system.evaluate(exec_intent, event)

                session.system_state.emit_delta("risk", risk_state)


        except WebSocketDisconnect:

            print("[INTENT_WS] disconnected:", session_id)
            break


        except Exception as e:

            print("[INTENT_WS][ERROR]", repr(e))

            try:
                await websocket.send_json({
                    "type": "EXECUTION_ERROR",
                    "error": str(e)
                })
            except:
                pass