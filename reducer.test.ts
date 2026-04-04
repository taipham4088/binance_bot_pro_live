// reducer.test.ts
import { reduce, SystemState, SnapshotMessage, DeltaMessage } from "./reducer";

function baseState(): SystemState {
  return {
    meta: { session_id: "s1", seq: 0, last_update_ts: 0, mode: "SNAPSHOT" },
    system: { status: "RUNNING", authority: "LIVE_READONLY" },
    execution: { active_orders: [], positions: [] },
    risk: { state: "OK" },
    account: {},
    analytics: {},
    health: {},
  };
}

test("SNAPSHOT initializes state", () => {
  const snap: SnapshotMessage = {
    mode: "SNAPSHOT",
    session_id: "s1",
    seq: 1,
    ts: 100,
    state: baseState(),
  };

  const state = reduce(null, snap);
  expect(state.meta.seq).toBe(1);
  expect(state.meta.mode).toBe("SNAPSHOT");
});

test("DELTA before SNAPSHOT throws", () => {
  const delta: DeltaMessage = {
    mode: "DELTA",
    session_id: "s1",
    seq: 1,
    ts: 100,
    patch: [],
  };

  expect(() => reduce(null, delta)).toThrow("DELTA_BEFORE_SNAPSHOT");
});

test("DELTA applies patch", () => {
  const snap: SnapshotMessage = {
    mode: "SNAPSHOT",
    session_id: "s1",
    seq: 1,
    ts: 100,
    state: baseState(),
  };

  const delta: DeltaMessage = {
    mode: "DELTA",
    session_id: "s1",
    seq: 2,
    ts: 200,
    patch: [
      { op: "replace", path: "/risk/state", value: "FROZEN" },
    ],
  };

  const s1 = reduce(null, snap);
  const s2 = reduce(s1, delta);

  expect(s2.risk.state).toBe("FROZEN");
  expect(s2.meta.seq).toBe(2);
});

test("Lower seq delta is ignored", () => {
  const s0 = baseState();
  s0.meta.seq = 5;

  const delta: DeltaMessage = {
    mode: "DELTA",
    session_id: "s1",
    seq: 4,
    ts: 200,
    patch: [
      { op: "replace", path: "/risk/state", value: "FROZEN" },
    ],
  };

  const s1 = reduce(s0, delta);
  expect(s1).toBe(s0);
});

test("Invariant warning detected", () => {
  const snap: SnapshotMessage = {
    mode: "SNAPSHOT",
    session_id: "s1",
    seq: 1,
    ts: 100,
    state: {
      ...baseState(),
      execution: { last_action: { type: "TRADE" } },
    },
  };

  const state = reduce(null, snap);
  expect(state.meta.warnings).toContain("TRADE_WHILE_READONLY");
});
