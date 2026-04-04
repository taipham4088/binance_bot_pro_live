import { useState } from "react"
import { Session } from "./types/session"
import SessionListPanel from "./components/SessionListPanel"
import SessionDetailPanel from "./components/SessionDetailPanel"

const MOCK_SESSIONS: Record<string, Session> = {
  live1: {
    id: "478ead8c-e174-43e6-9b1e-c812b207fe77",
    mode: "live",
    status: "running",
    config: {
      engine: "dual_engine",
      engine_profile: "momentum",
      position_mode: "long_only",
      symbol: "BTCUSDT",
      mode: "live"
    }
  },
  paper1: {
    id: "paper-001",
    mode: "paper",
    status: "idle",
    config: {
      engine: "dual_engine",
      engine_profile: "range_trend",
      position_mode: "dual",
      symbol: "ETHUSDT",
      mode: "paper"
    }
  }
}

export default function App() {
  const [sessions, setSessions] = useState(MOCK_SESSIONS)
  const [focusedSessionId, setFocusedSessionId] = useState<string>("live1")

  return (
    <div style={{ display: "flex" }}>
      <SessionListPanel
        sessions={sessions}
        focusedSessionId={focusedSessionId}
        onSelect={setFocusedSessionId}
      />

      <SessionDetailPanel
        session={sessions[focusedSessionId]}
        onSessionUpdate={(updated) =>
          setSessions({ ...sessions, [updated.id]: updated })
        }
      />
    </div>
  )
}
