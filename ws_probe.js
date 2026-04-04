const ws = new WebSocket("ws://127.0.0.1:8000/ws/state/478ead8c-e174-43e6-9b1e-c812b207fe77");

ws.onopen = () => console.log("WS OPEN");
ws.onmessage = (m) => console.log("MSG:", m.data);
ws.onerror = (e) => console.error("ERR", e);
ws.onclose = () => console.log("CLOSE");
