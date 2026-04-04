type Level = "OK" | "WARN" | "CRITICAL";

export function PanelHeader({
  title,
  level = "OK",
  icon,
}: {
  title: string;
  level?: Level;
  icon?: string;
}) {
  const color =
    level === "CRITICAL"
      ? "red"
      : level === "WARN"
      ? "orange"
      : "inherit";

  return (
    <h3 style={{ color, display: "flex", alignItems: "center", gap: 6 }}>
      {title}
      {icon && <span title={level}>{icon}</span>}
    </h3>
  );
}

