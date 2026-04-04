// state_store.ts
import { reduce, StateMessage } from "./reducer";
import { compareStates, Divergence } from "./replay/session_compare";
import { SystemState } from "./reducer";
import { WSClient } from "./ws_client";
import { runReplay } from "./replay/replayRunner";
export type ConnectionStatus =
  | "DISCONNECTED"
  | "CONNECTING"
  | "SNAPSHOT_OK"
  | "LIVE"
  | "DEGRADED"
  | "ERROR";

type StatusListener = (status: ConnectionStatus) => void;

type StateListener = (state: SystemState) => void;

export class SessionStore {
  private state: SystemState | null = null;
  private listeners: Set<StateListener> = new Set();
  private wsClient: WSClient;
  private status: ConnectionStatus = "DISCONNECTED";
  private statusListeners: Set<StatusListener> = new Set();

  constructor(wsUrl: string, sessionId: string) {
    this.wsClient = new WSClient({
      url: wsUrl,
      sessionId,
      onState: (message: StateMessage) => {
        this.state = reduce(this.state, message);
        if (this.state) {
          this.listeners.forEach(cb => cb(this.state!));
        }
      },
      
      onStatusChange: (status) => this.updateStatus(status),
      onError: (err) => console.error("[WS]", sessionId, err),
    });
  }

  connect() {
    console.log("[SessionStore] connect()");
    this.wsClient.connect();
    // DEBUG ONLY – xoá sau
    (window as any)['__sessionStore'] = this;
  }
    
    disconnect() {
    this.wsClient.disconnect();
  }

  private updateState(state: SystemState) {
    this.state = state;
    this.listeners.forEach((cb) => cb(state));
  }

  private updateStatus(status: ConnectionStatus) {
    this.status = status;
    this.statusListeners.forEach((cb) => cb(status));
  }

  subscribe(cb: StateListener): () => void {
    this.listeners.add(cb);
    if (this.state) cb(this.state); // push current state immediately
    return () => this.listeners.delete(cb);
  }

  getState(): SystemState | null {
    return this.state;
  }

  subscribeStatus(cb: StatusListener): () => void {
    this.statusListeners.add(cb);
    cb(this.status); // push current status immediately
    return () => this.statusListeners.delete(cb);
  }

  getStatus(): ConnectionStatus {
    return this.status;
  }
  // ===== C2: Replay offline =====
  getReplayState(): SystemState | null {
    // lấy toàn bộ message thật đã ghi từ WSClient
    const messages = this.wsClient.getRecordedMessages();

    if (!messages || messages.length === 0) {
      return null;
    }

    return runReplay(messages);
  }
  // ===== C3: Compare LIVE vs REPLAY =====
  compareWithReplay(): Divergence | null {
    const live = this.getState();
    const replay = this.getReplayState();

    if (!live || !replay) return null;

    return compareStates(live, replay);
  }
}
