import { setDevOverride } from "./devStateOverride";

export function DevPanel({ state }: { state: any }) {
  return (
    <div
      style={{
        marginTop: 8,
        padding: 8,
        border: "1px dashed #aaa",
        fontSize: 12,
      }}
    >
      <strong>DEV</strong>{" "}
      <button
        onClick={() => {
          const fake = JSON.parse(JSON.stringify(state));
          fake.risk.state = "FROZEN";
          fake.health.level = "CRITICAL";
          fake.health.components.risk = "DOWN";
          setDevOverride(fake);
        }}
      >
        Simulate Risk
      </button>

      <button
        style={{ marginLeft: 8 }}
        onClick={() => setDevOverride(null)}
      >
        Clear
      </button>
    </div>
  );
}
