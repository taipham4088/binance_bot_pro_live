import { useState } from "react";

type Props = {
  sessions: string[];
  activeSession: string;
  onSelect: (sessionId: string) => void;
};

export function SessionSwitcher({
  sessions,
  activeSession,
  onSelect,
}: Props) {
  return (
    <div style={{ marginBottom: 8 }}>
      <label>Session: </label>
      <select
        value={activeSession}
        onChange={(e) => onSelect(e.target.value)}
      >
        {sessions.map((id) => (
          <option key={id} value={id}>
            {id}
          </option>
        ))}
      </select>
    </div>
  );
}
