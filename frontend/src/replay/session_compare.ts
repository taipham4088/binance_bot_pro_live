// session_compare.ts
import { SystemState } from "../reducer";
// ===== Whitelist rules =====

// exact paths
const EXACT_WHITELIST = new Set<string>([
  "meta.last_update_ts",
  "system.uptimeSec",
  "system.uptime",
  "system.started_at",
]);

// prefix paths
const PREFIX_WHITELIST = [
  "health.",
  "system.last_event",
  "system.flags",
  "analytics.last_update",
];

// dynamic keys (suffix-based)
function isDynamicKey(path: string) {
  return (
    path.endsWith(".ts") ||
    path.endsWith(".last_update") ||
    path.endsWith(".last_heartbeat")
  );
}

function isWhitelisted(path: string): boolean {
  if (EXACT_WHITELIST.has(path)) return true;

  for (const p of PREFIX_WHITELIST) {
    if (path.startsWith(p)) return true;
  }

  if (isDynamicKey(path)) return true;

  return false;
}

export type Divergence = {
  path: string;
  live: any;
  replay: any;
};

function isObject(v: any) {
  return typeof v === "object" && v !== null;
}

export function compareStates(
  live: SystemState,
  replay: SystemState
): Divergence | null {
  return diffRecursive(live, replay, "");
}

function diffRecursive(
  a: any,
  b: any,
  path: string
): Divergence | null {
  // primitive
  if (!isObject(a) || !isObject(b)) {
    if (a !== b) {
      if (isWhitelisted(path)) {
        return null;
      }
      return { path, live: a, replay: b };
    }
    return null;
  }


  // arrays
  if (Array.isArray(a) || Array.isArray(b)) {
    if (JSON.stringify(a) !== JSON.stringify(b)) {
      if (isWhitelisted(path)) {
        return null;
      }
      return { path, live: a, replay: b };
    }
    return null;
  }


  // objects
  const keys: Record<string, true> = {};

  Object.keys(a).forEach((k) => (keys[k] = true));
  Object.keys(b).forEach((k) => (keys[k] = true));

  for (const k in keys) {
    const nextPath = path ? `${path}.${k}` : k;
    const d = diffRecursive(a[k], b[k], nextPath);
    if (d) return d;
  }

  return null;
}
