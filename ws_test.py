import requests
import websocket
import json
import time

# tạo session mới


SESSION_ID = "478ead8c-e174-43e6-9b1e-c812b207fe77"  # session đã live/start
URL = f"ws://127.0.0.1:8000/ws/state/{SESSION_ID}"

ws = websocket.WebSocket()
ws.connect(URL)

print("✅ Connected to", URL)
count = 0

while True:
    try:
        msg = ws.recv()   # 🔥 DÒNG QUYẾT ĐỊNH
        count += 1

        data = json.loads(msg)

        print(f"\n📩 MESSAGE #{count}")
        print("  type =", data.get("type"))
        print("  mode =", data.get("mode"))
        print("  system.state =", data.get("system", {}).get("state"))
        print("  payload_empty =", data.get("system") == {})
        print(json.dumps(data, indent=2))
    except Exception as e:
        print("❌ WS error:", e)
        break
