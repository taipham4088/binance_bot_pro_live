import { useState, useEffect } from "react";
import "./dashboard.css";

import { useTheme } from "./theme/ThemeContext";
import { useI18n } from "./i18n/I18nContext";

import {
  getDevOverride,
  subscribeDevOverride,
} from "./dev/devStateOverride";

import { SessionSwitcher } from "./SessionSwitcher";
import { HealthIndicator } from "./HealthIndicator";

import {
  mapSystemPanel,
  mapRiskPanel,
  mapExecutionPanel,
  mapAccountPanel,
} from "./panel_mapper";

import { ReplayTimelineView } from "./ReplayTimelineView";
import { SessionCompareView } from "./SessionCompareView";
import { HealthPanel } from "./components/HealthPanel";
import { DevPanel } from "./dev/DevPanel";
import { PanelHeader } from "./components/PanelHeader";

export function Dashboard({
  state,
  status,
  sessions,
  activeSession,
  setActiveSession,
  timeline,
}: any) {
  // ===== REACT CORE =====
  const [, forceRender] = useState(0);

  useEffect(() => {
    return subscribeDevOverride(() => {
      forceRender((x) => x + 1);
    });
  }, []);

  // ===== APP CONTEXT =====
  const { theme, setTheme } = useTheme();
  const { lang, setLang, t } = useI18n();

  // ===== DERIVED STATE (D1.4) =====
  const effectiveState = getDevOverride() ?? state;
  // ===== EXECUTION LEVEL DERIVED =====
  const execStatus = effectiveState?.execution?.status;

  let execLevel: "OK" | "WARN" | "CRITICAL" = "OK";

  if (execStatus === "FROZEN") execLevel = "CRITICAL";
  else if (execStatus === "DEGRADED") execLevel = "WARN";
  else if (execStatus === "READY") execLevel = "OK";

  // ===== SNAPSHOT GATE =====
  if (!state) {
    switch (status) {
      case "CONNECTING":
        return <div>Connecting…</div>;
      case "READY_SENT":
        return <div>Handshaking…</div>;
      case "SNAPSHOT_OK":
        return <div>Applying snapshot…</div>;
      case "DISCONNECTED":
        return <div>Disconnected</div>;
      default:
        return <div>Waiting SNAPSHOT…</div>;
    }
  }

  return (
    <div className="dashboard">
      {/* ================= HEADER ================= */}
      <div className="header">
        {/* LEFT: session + health */}
        <SessionSwitcher
          sessions={sessions}
          activeSession={activeSession}
          onSelect={setActiveSession}
        />

        <HealthIndicator state={effectiveState} />

        {status === "DEGRADED" && (
          <div style={{ color: "orange", marginLeft: 8 }}>
            ⚠ Connection unstable
          </div>
        )}

        {/* RIGHT: language + theme */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {/* LANGUAGE */}
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value as "vi" | "en")}
          >
            <option value="vi">VI</option>
            <option value="en">EN</option>
          </select>

          {/* THEME */}
          <button
            onClick={() =>
              setTheme(theme === "dark" ? "light" : "dark")
            }
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </div>
      </div>

      {/* ================= DEV PANEL ================= */}
      {process.env.NODE_ENV === "development" && (
        <DevPanel state={effectiveState} />
      )}

      {/* ================= INFRASTRUCTURE ================= */}
      <div className="domain">
        <h2>Infrastructure</h2>

        {/* SYSTEM */}
        <div className="panel">
          <PanelHeader title={t.system} level="OK" />
          <pre>
            {JSON.stringify(mapSystemPanel(effectiveState), null, 2)}
          </pre>
        </div>

        {/* SOURCES STUB */}
        <div className="panel">
          <PanelHeader title="Sources" level="OK" />
          <pre>
            {JSON.stringify(
              [
                { client: "client_1", mode: "LIVE", status: "Connected" },
                { client: "client_2", mode: "REPLAY", status: "Connected" },
                { client: "client_3", mode: "UNKNOWN", status: "Connected" },
              ],
              null,
              2
            )}
          </pre>
        </div>
      </div>

      {/* ================= OPERATIONAL ================= */}
      <div className="domain">
        <h2>Operational</h2>

        {/* RISK */}
        <div className="panel">
          <PanelHeader
            title={t.Risk}
            level={
              effectiveState.risk?.state === "FROZEN" ? "CRITICAL" : "OK"
            }
          />
          <pre>
            {JSON.stringify(mapRiskPanel(effectiveState), null, 2)}
          </pre>
        </div>

        {/* EXECUTION */}
        <div className="panel">
          <PanelHeader title={t.Execution} level={execLevel} />

          {effectiveState.execution?.reason && (
            <div style={{ color: "red", fontWeight: "bold", marginBottom: 8 }}>
              {effectiveState.execution.reason}
            </div>
          )}

          <pre>
            {JSON.stringify(mapExecutionPanel(effectiveState), null, 2)}
          </pre>
        </div>

        {/* ACCOUNT */}
        <div className="panel">
          <PanelHeader title={t.Account} level="OK" />
          <pre>
            {JSON.stringify(mapAccountPanel(effectiveState), null, 2)}
          </pre>
        </div>
      </div>

      {/* ================= OBSERVABILITY ================= */}
      <div className="domain">
        <h2>Observability</h2>

        {/* HEALTH */}
        <div className="panel">
          <HealthPanel health={effectiveState.health} />
        </div>

        {/* TIMELINE */}
        <div className="panel">
          <h3>{t.ReplayTimeline}</h3>
          <ReplayTimelineView timeline={timeline} />
        </div>

        {/* SESSION COMPARE */}
        <div className="panel">
          <h3>{t.SessionCompare}</h3>
          <SessionCompareView />
        </div>
      </div>
      
    </div>
  );
}
