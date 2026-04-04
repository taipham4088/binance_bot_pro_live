import { SystemState } from "../reducer";

let override: SystemState | null = null;
const listeners = new Set<() => void>();

export function setDevOverride(state: SystemState | null) {
  override = state;
  listeners.forEach((cb) => cb());
}

export function getDevOverride(): SystemState | null {
  return override;
}

export function subscribeDevOverride(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  }  
}
