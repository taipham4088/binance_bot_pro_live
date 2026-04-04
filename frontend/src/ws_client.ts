// ws_client.ts
import { StateMessage } from "./reducer";
import { SessionRecorder } from "./replay/sessionRecorder";

export type ConnectionStatus =
  | "DISCONNECTED"
  | "CONNECTING"
  | "SNAPSHOT_OK"
  | "LIVE"
  | "DEGRADED"
  | "ERROR";

type WSClientOptions = {
  url: string;
  sessionId: string;
  reconnectDelayMs?: number;
  onState?: (message: StateMessage) => void;
  onError?: (err: any) => void;
  onStatusChange?: (status: ConnectionStatus) => void;
};

export class WSClient {
  private ws: WebSocket | null = null;
  private recorder = new SessionRecorder();
  private reconnectDelay: number;
  private closedByUser = false;
  private status: ConnectionStatus = "DISCONNECTED";
  private lastMessageTs = 0;
  private heartbeatTimer?: number;

  constructor(private opts: WSClientOptions) {
    console.log("[WSClient] constructor", opts.url, opts.sessionId);
    this.reconnectDelay = opts.reconnectDelayMs ?? 2000;
  }

  private setStatus(next: ConnectionStatus) {
    if (this.status === next) return;
    this.status = next;
    this.opts.onStatusChange?.(next);
  }

  connect() {
    this.closedByUser = false;
    this.setStatus("CONNECTING");
    this.openWS();
  }

  disconnect() {
    this.closedByUser = true;
    this.ws?.close();
  }

  private openWS() {
    const wsUrl = `${this.opts.url}/ws/state/${this.opts.sessionId}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.recorder.reset();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const message: StateMessage = JSON.parse(event.data);
        this.lastMessageTs = Date.now();

        this.recorder.record(message);
        this.opts.onState?.(message);

        if (message.type === "SNAPSHOT") {
          this.setStatus("SNAPSHOT_OK");
          this.startHeartbeatMonitor();
        } else {
          this.setStatus("LIVE");
        }
      } catch (err) {
        this.setStatus("ERROR");
        this.opts.onError?.(err);
      }
    };

    this.ws.onclose = () => {
      this.cleanup();
      if (this.closedByUser) return;

      this.setStatus("DISCONNECTED");
      setTimeout(() => this.openWS(), this.reconnectDelay);
    };

    this.ws.onerror = (err) => {
      this.opts.onError?.(err);
    };
  }

  private startHeartbeatMonitor() {
    if (this.heartbeatTimer) return;

    this.heartbeatTimer = window.setInterval(() => {
      const diff = Date.now() - this.lastMessageTs;
      if (diff > 3000 && this.status === "LIVE") {
        this.setStatus("DEGRADED");
      } else if (diff <= 3000 && this.status === "DEGRADED") {
        this.setStatus("LIVE");
      }
    }, 1000);
  }

  private cleanup() {
    this.lastMessageTs = 0;
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = undefined;
    }
  }

  getRecordedMessages(): StateMessage[] {
    return this.recorder.getAll();
  }
}
