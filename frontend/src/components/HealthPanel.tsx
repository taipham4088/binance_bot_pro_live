import React from "react";

type HealthLevel = "OK" | "WARN" | "CRITICAL";
type HealthComponentState = "OK" | "DEGRADED" | "DOWN";

interface Health {
  level: HealthLevel;
  components: Record<string, HealthComponentState>;
}

function colorOf(v: HealthComponentState | HealthLevel) {
  if (v === "OK") return "green";
  if (v === "WARN" || v === "DEGRADED") return "orange";
  return "red";
}

export function HealthPanel({ health }: { health?: Health }) {
  const healthClass =
    health?.level === "CRITICAL"
      ? "health-critical"
      : health?.level === "WARN"
      ? "health-warn"
      : "health-ok";
  if (!health) {
    return (
      <div className={`panel ${healthClass}`}>
        <h3>Health</h3>
        <div style={{ color: "gray" }}>No health data</div>
      </div>
    );
  }

  return (
    <div className={`panel ${healthClass}`}>
      <h3>Health</h3>

      <div style={{ marginBottom: 8 }}>
        <strong>Overall:</strong>{" "}
        <span style={{ color: colorOf(health.level) }}>
          {health.level}
        </span>
      </div>

      <div>
        {Object.entries(health.components).map(([name, state]) => (
          <div key={name}>
            <strong>{name}:</strong>{" "}
            <span style={{ color: colorOf(state) }}>{state}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
