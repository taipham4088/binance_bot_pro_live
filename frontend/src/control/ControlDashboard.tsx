import { useEffect, useState } from "react"
import { Session } from "../types/session"
import SessionListPanel from "./components/SessionListPanel"
import SessionDetailPanel from "./components/SessionDetailPanel"
import { listSessions, createSession } from "./api/sessionApi"

export default function ControlDashboard() {
  // ===== STATE =====
  const [sessions, setSessions] = useState<Record<string, Session>>({})
  const [focusedSessionId, setFocusedSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // ===== FETCH EXISTING SESSIONS (STEP 3) =====
  useEffect(() => {
    listSessions()
      .then((data) => {
        setSessions(data)
        const firstId = Object.keys(data)[0] || null
        setFocusedSessionId(firstId)
        setLoading(false)
      })
      .catch((e) => {
        setError(e.message || "Failed to load sessions")
        setLoading(false)
      })
  }, [])

  // ===== CREATE PAPER / BACKTEST SESSION (STEP 2) =====
  const handleCreateSession = async (mode: "paper" | "backtest") => {
    try {
      const newSession = await createSession(mode)

      setSessions((prev) => ({
        ...prev,
        [newSession.id]: newSession,
      }))

      setFocusedSessionId(newSession.id)
    } catch (err) {
      alert("Create session failed")
    }
  }

  // ===== GUARD RENDER =====
  if (loading) return <div>Loading sessions...</div>
  if (error) return <div style={{ color: "red" }}>{error}</div>
  if (!focusedSessionId) return <div>No session</div>

  // ===== RENDER =====
  return (
    <div style={{ display: "flex", height: "100%" }}>
      <SessionListPanel
        sessions={sessions}
        focusedSessionId={focusedSessionId}
        onSelect={setFocusedSessionId}
        onCreateSession={handleCreateSession}
      />

      <SessionDetailPanel
        key={focusedSessionId}
        session={sessions[focusedSessionId]}
        onSessionUpdate={(s: Session) =>
          setSessions((prev) => ({ ...prev, [s.id]: s }))
        }
      />
    </div>
  )
}
