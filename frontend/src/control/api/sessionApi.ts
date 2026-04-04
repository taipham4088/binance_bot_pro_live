import { Session } from "../../types/session";

const API_BASE = "http://127.0.0.1:8000";

// ===== LIST SESSIONS =====
export async function listSessions(): Promise<Record<string, Session>> {
  const res = await fetch(`${API_BASE}/system/session/list`);

  if (!res.ok) {
    throw new Error("Failed to list sessions");
  }

  return res.json();
}

// ===== CREATE SESSION =====
export async function createSession(
  mode: "paper" | "backtest"
): Promise<Session> {
  const res = await fetch(`${API_BASE}/system/session/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode,
      symbol: "BTCUSDT",
      engine: "dual_engine",
    }),
  });

  if (!res.ok) {
    throw new Error("Failed to create session");
  }

  const data = await res.json();

  return {
    id: data.session_id,
    mode: data.mode,
    status: "idle",
    config: {
      engine: "dual_engine",
      engine_profile: "momentum",
      position_mode: "long_only",
      symbol: "BTCUSDT",
      mode: data.mode,
    },
  };
}
