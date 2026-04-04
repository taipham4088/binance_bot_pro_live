const WebSocket = require("ws");

const WS_URL = "ws://localhost:8000/ws/intent/live_shadow";

const SYMBOL = "BTCUSDT";
const QTY = 0.007;
const CYCLES = 10; // chạy 10 trước

let currentCycle = 0;
let currentSide = "LONG";

const ws = new WebSocket(WS_URL);

ws.on("open", () => {
    console.log("Connected to server");
    sendIntent();
});

ws.on("message", (data) => {
    const msg = data.toString();
    console.log("SERVER:", msg);

    // Chỉ tiếp tục khi execution hoàn tất
    if (msg.includes("EXECUTION_COMPLETED")) {
        currentCycle++;

        if (currentCycle >= CYCLES) {
            console.log("Reverse stress test DONE");
            ws.close();
            return;
        }

        // đảo chiều
        currentSide = currentSide === "LONG" ? "SHORT" : "LONG";

        setTimeout(() => {
            sendIntent();
        }, 300); // delay nhẹ cho an toàn
    }

    if (msg.includes("FROZEN")) {
        console.log("System FROZEN — STOP TEST");
        ws.close();
    }
});

ws.on("close", () => {
    console.log("WebSocket closed");
});

ws.on("error", (err) => {
    console.error("WebSocket error:", err.message);
});

function sendIntent() {
    console.log(`Cycle ${currentCycle + 1} → ${currentSide}`);

    const message = {
        type: "SET_POSITION",
        payload: {
            symbol: SYMBOL,
            side: currentSide,
            qty: QTY
        }
    };

    ws.send(JSON.stringify(message));
}