import { HealthPoint } from "./health_timeline";

const COLORS: Record<string, string> = {
  OK: "#2ecc71",
  WARN: "#f1c40f",
  CRITICAL: "#e74c3c",
};

export function HealthTimelineOverlay({
  points,
  current,
}: {
  points: HealthPoint[];
  current: number;
}) {
  return (
    <div style={{ display: "flex", height: 10, marginBottom: 8 }}>
      {points.map((p) => (
        <div
          key={p.index}
          style={{
            flex: 1,
            backgroundColor: COLORS[p.level],
            opacity: p.index === current ? 1 : 0.4,
          }}
          title={`#${p.index} – ${p.level}`}
        />
      ))}
    </div>
  );
}
