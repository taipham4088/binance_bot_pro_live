// reducer.ts
import { applyPatch, Operation } from "fast-json-patch";

export type RiskState = "OK" | "FROZEN" | "BLOCKED";
export type ExecutionStatus =
  | "INIT"
  | "BOOTSTRAPPING"
  | "SYNCING"
  | "READY"
  | "DEGRADED"
  | "FROZEN";

export interface RiskStateV1 {
  state: RiskState;
  violations: string[];
  limits: Record<string, any>;
}

export interface HealthStateV1 {
  level: "OK" | "WARN" | "CRITICAL";
  components: Record<string, "OK" | "DEGRADED" | "DOWN">;
}

export interface ExecutionStateV1 {
  status: ExecutionStatus;
  reason?: string | null;
  since?: number;
  uptime?: number;

  positions: any[];
  activeOrders: any[];
  lastAction: any | null;
}

export type MessageMode = "SNAPSHOT" | "DELTA";

export interface Meta {
  session_id: string;
  seq: number;
  last_update_ts: number;
  mode: MessageMode;
  warnings?: string[];
}

export interface SystemState {
  meta: Meta;

  system: {
    state: string;
    mode?: string;
    authority?: string;
  };

  execution: ExecutionStateV1;
  risk: RiskStateV1;
  account?: Record<string, any>;
  analytics?: Record<string, any>;

  health: HealthStateV1;
}

export interface SnapshotMessage {
  type: "SNAPSHOT";
  data: SystemState;
}

export interface DeltaMessage {
  type: "DELTA";
  data: {
    patch: Operation[];
  };
}

export type StateMessage = SnapshotMessage | DeltaMessage;

function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj));
}

export function reduce(
  currentState: SystemState | null,
  message: StateMessage
): SystemState | null {

  // 1️⃣ SNAPSHOT = replace toàn bộ
  if (message.type === "SNAPSHOT") {
    return deepClone(message.data);
  }

  // 2️⃣ DELTA trước SNAPSHOT → ignore
  if (currentState === null && message.type === "DELTA") {
    console.warn("[Reducer] DELTA before SNAPSHOT – ignored");
    return currentState;
  }

  // 3️⃣ Apply JSON Patch
  if (message.type === "DELTA") {
    try {
      const patched = applyPatch(
        deepClone(currentState!),
        message.data.patch,
        true,
        false
      ).newDocument as SystemState;

      return patched;
    } catch (err) {
      console.error("PATCH_APPLY_FAILED", err);
      return currentState;
    }
  }

  return currentState;
}


