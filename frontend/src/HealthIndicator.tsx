import { evaluateHealth } from "./health_evaluator";
import { SystemState } from "./reducer";

const COLORS: Record<string, string> = {
  OK: "green",
  WARN: "orange",
  CRITICAL: "red",
};

export function HealthIndicator({ state }: { state: SystemState }) {
  const { level, reasons } = evaluateHealth(state);

  return (
    <div style={{ marginBottom: 8 }}>
      <span
        style={{
          display: "inline-block",
          width: 12,
          height: 12,
          borderRadius: "50%",
          backgroundColor: COLORS[level],
          marginRight: 8,
        }}
      />
      <b>{level}</b>

      {reasons.length > 0 && (
        <ul>
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
