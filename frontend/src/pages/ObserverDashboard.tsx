import "../intent_client";
import { intentClient } from "../intent_client";
import { useEffect, useRef, useState } from "react";
import { ThemeProvider } from "../theme/ThemeContext";
import { I18nProvider } from "../i18n/I18nContext";
import { Dashboard } from "../Dashboard";
import { DashboardStore } from "../dashboard_store";
import { SystemState } from "../reducer";
import { ReplayTimeline } from "../replay_timeline";
import { ReplayReader } from "../replay_reader";
import { ConnectionStatus } from "../state_store";

const WS_URL = "ws://127.0.0.1:8000";
const SESSIONS = ["live_shadow"];
const DEFAULT_SESSION = "live_shadow";


const replayReader = new ReplayReader();
const timeline = new ReplayTimeline(replayReader);

export default function ObserverDashboard() {
  console.log("[ObserverDashboard] mounted");

  const [state, setState] = useState<SystemState | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("DISCONNECTED");
  const [sessions] = useState<string[]>(SESSIONS);
  const [activeSession, setActiveSession] =
    useState<string>(DEFAULT_SESSION);

  // ✅ GUARD: đảm bảo intentClient.connect chỉ chạy 1 lần
  const intentConnectedRef = useRef(false);

  useEffect(() => {
    const store = new DashboardStore(WS_URL);

    const unsubscribers: Array<() => void> = [];

    SESSIONS.forEach((sessionId) => {
      const sessionStore = store.addSession(sessionId);
      const unsubState = sessionStore.subscribe((s: any) => {
        console.log("[DEBUG STATE FROM STORE]", s);
        // 👉 CHỈ UPDATE UI KHI LÀ SESSION ĐANG ACTIVE
        if (sessionId !== activeSession) return;
        const snapshot = s.data ?? s;
        const adapted: SystemState = {
          meta: {
            session_id: sessionId,
            seq: s.seq ?? 0,
            last_update_ts: Date.now(),
            mode: "SNAPSHOT",
          },

          system: {
            state: snapshot.system?.state ?? "UNKNOWN",
            authority: snapshot.system?.authority ?? "UNKNOWN",
          },

          execution: {
            status: snapshot.execution?.status ?? "UNKNOWN",
            reason: snapshot.execution?.reason ?? null,
            since: snapshot.execution?.since,
            uptime: snapshot.execution?.uptime,

            positions: snapshot.execution?.positions ?? [],
            activeOrders: snapshot.execution?.activeOrders ?? [],
            lastAction: snapshot.execution?.lastAction ?? null,
          },

          risk: snapshot.risk ?? {
            state: "OK",
            violations: [],
            limits: {},
          },

          account: snapshot.account ?? {
            balance: 0,
            equity: 0,
            margin: 0,
          },

          analytics: snapshot.analytics ?? {},

          health: {
            level: snapshot.health?.level ?? "OK",
            components: snapshot.health?.components ?? {},
          },
        };

        setState(adapted);
      });

      const unsubStatus = sessionStore.subscribeStatus(
        (st: ConnectionStatus) => {
          if (sessionId === activeSession) {
            setStatus(st);
          }
        }
      );

      unsubscribers.push(unsubState, unsubStatus);
    });


    // ===== FIX 1: CONNECT INTENT WS CHỈ 1 LẦN =====
    if (!intentConnectedRef.current) {
      intentClient.connect(DEFAULT_SESSION);
      intentConnectedRef.current = true;
      console.log("[INTENT] WS connect() called ONCE");
    } else {
      console.log("[INTENT] WS connect() skipped (already connected)");
    }
    // ============================================

    return () => {
      unsubscribers.forEach((fn) => fn());
    };

  }, []);

  if (!state) {
    return (
      <ThemeProvider>
        <I18nProvider>
          <div style={{ padding: 16 }}>
            Waiting SNAPSHOT…
          </div>
        </I18nProvider>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <I18nProvider>
        <Dashboard
          state={state}
          status={status}
          sessions={sessions}
          activeSession={activeSession}
          setActiveSession={setActiveSession}
          timeline={timeline}
        />
      </I18nProvider>
    </ThemeProvider>
  );
}
