import { Session } from "../../types/session"


type Props = {
  sessions: Record<string, Session>;
  focusedSessionId: string;
  onSelect: (id: string) => void;
  onCreateSession: (mode: "paper" | "backtest") => void;
};

export default function SessionListPanel({
  sessions,
  focusedSessionId,
  onSelect,
}: Props) {
  return (
    <div style={{ width: 240, borderRight: "1px solid #ccc" }}>
      <h3>Sessions</h3>
      {/* === CREATE SESSION BUTTONS === */}
      <div style={{ padding: 8 }}>
       <button style={{ marginRight: 8 }}>+ Paper</button>
       <button>+ Backtest</button>
      </div>

      {/* === SESSION LIST === */}
      {Object.values(sessions).map((s) => (
        <div
          key={s.id}
          onClick={() => onSelect(s.id)}
          style={{
            padding: 8,
            cursor: "pointer",
            background: s.id === focusedSessionId ? "#eee" : "transparent",
          }}
        >
          {s.mode.toUpperCase()} | {s.config.symbol}
        </div>
      ))}
    </div>
  );
}
