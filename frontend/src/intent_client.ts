class IntentClient {
  ws: WebSocket | null = null;
  sessionId: string | null = null;

  connect(sessionId: string) {
    // 🚫 nếu đang dùng cùng session + ws còn open → KHÔNG làm gì
    if (
      this.ws &&
      this.ws.readyState === WebSocket.OPEN &&
      this.sessionId === sessionId
    ) {
      return;
    }

    // 🚫 nếu có ws cũ → close rõ ràng
    if (this.ws) {
      try {
        this.ws.close();
      } catch {}
      this.ws = null;
    }

    this.sessionId = sessionId;

    const ws = new WebSocket(
      `ws://127.0.0.1:8000/ws/intent/${sessionId}`
    );

    this.ws = ws;

    ws.onopen = () => {
      console.log("[INTENT] WS open");
    };

    ws.onclose = () => {
      console.log("[INTENT] WS closed");
      this.ws = null;
    };

    ws.onerror = (e) => {
      console.error("[INTENT] WS error", e);
    };

    // ===== DEV HOOK – CHỐT PHASE 1.5 =====
    if (process.env.NODE_ENV === "development") {
      (window as any).__INTENT_SEND__ = (payload: any) => {
        console.log(
          "[INTENT DEV] using ws",
          this.ws,
          "readyState=",
          this.ws?.readyState
        );

        if (!this.ws) {
          console.warn("[INTENT DEV] ws not exist");
          return;
        }

        if (this.ws.readyState !== WebSocket.OPEN) {
          console.warn(
            "[INTENT DEV] ws not open",
            this.ws.readyState
          );
          return;
        }

        console.log("[INTENT DEV] send", payload);
        this.ws.send(JSON.stringify(payload));
      };


      console.log("[INTENT DEV] __INTENT_SEND__ registered");
    }
    // ====================================
  }

  send(payload: any) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn("[INTENT] send failed – ws not open");
      return;
    }

    console.log("[INTENT][SEND]", payload);
    this.ws.send(JSON.stringify(payload));
  }
}

// ===== GLOBAL SINGLETON (BẮT BUỘC) =====
const g = window as any;

export const intentClient: IntentClient =
  g.__INTENT_CLIENT__ ?? new IntentClient();

g.__INTENT_CLIENT__ = intentClient;
// =====================================
