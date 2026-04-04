const WebSocket = require("ws");

const SESSION_ID = "478ead8c-e174-43e6-9b1e-c812b207fe77";
const ws = new WebSocket(`ws://127.0.0.1:8000/ws/state/${SESSION_ID}`);

ws.on("open", () => {
  console.log("✅ WS connected");
});

ws.on("message", (data) => {
  console.log("📩 WS message:", data.toString());
});

ws.on("close", () => {
  console.log("❌ WS closed");
});

ws.on("error", (err) => {
  console.error("🔥 WS error:", err);
});
