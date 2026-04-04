// dashboard_store.ts
import { SessionStore } from "./state_store";

export class DashboardStore {
  private sessions: Map<string, SessionStore> = new Map();

  constructor(private wsUrl: string) {}

  addSession(sessionId: string): SessionStore {
    if (this.sessions.has(sessionId)) {
      return this.sessions.get(sessionId)!;
    }

    // ⭐ FIX: ensure ws:// protocol
    const wsUrl = this.wsUrl.replace(/^http/, "ws");

    const store = new SessionStore(wsUrl, sessionId);
    this.sessions.set(sessionId, store);
    store.connect();

    return store;
  }

  removeSession(sessionId: string) {
    const store = this.sessions.get(sessionId);
    if (!store) return;

    store.disconnect();
    this.sessions.delete(sessionId);
  }

  listSessions(): string[] {
    return Array.from(this.sessions.keys());
  }

  getSession(sessionId: string): SessionStore | undefined {
    return this.sessions.get(sessionId);
  }
}
