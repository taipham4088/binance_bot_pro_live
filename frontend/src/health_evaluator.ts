// health_evaluator.ts
import { SystemState } from "./reducer";

export type HealthLevel = "OK" | "WARN" | "CRITICAL";

export function evaluateHealth(state: SystemState): {
  level: HealthLevel;
  reasons: string[];
} {
  const reasons: string[] = [];
  // Defensive: state may be partial (before first full snapshot)
  if (!state) {
    return { level: "OK", reasons };
  }

  // Risk dominates
  if (
    state.risk &&
    (state.risk.state === "FROZEN" || state.risk.state === "BLOCKED")
  ) {
    reasons.push(`RISK_${state.risk.state}`);
    return { level: "CRITICAL", reasons };
  }

  // Invariant warnings
  if (state.meta && (state.meta.warnings ?? []).length > 0) {
    reasons.push(...state.meta.warnings!);
    return { level: "WARN", reasons };
  }

  // Health components
  const comps = state.health?.components ?? {};
  if (Object.values(comps).some((v) => v === "DOWN")) {
    reasons.push("COMPONENT_DOWN");
    return { level: "CRITICAL", reasons };
  }

  if (Object.values(comps).some((v) => v === "DEGRADED")) {
    reasons.push("COMPONENT_DEGRADED");
    return { level: "WARN", reasons };
  }

  return { level: "OK", reasons };
}
