// panel_mapper.ts
import { SystemState } from "./reducer";

/* ---------- SYSTEM PANEL ---------- */
export function mapSystemPanel(state: SystemState) {
  return {
    status: state.system?.state ?? "UNKNOWN",
    authority: state.system?.authority ?? null,
    uptimeSec: null,
  };
}

/* ---------- EXECUTION PANEL ---------- */
export function mapExecutionPanel(state: SystemState) {
  return {
    status: state.execution?.status ?? "UNKNOWN",
    reason: state.execution?.reason ?? null,
    positions: state.execution?.positions ?? [],
    activeOrders: state.execution?.activeOrders ?? [],
    lastAction: state.execution?.lastAction ?? null,
  };
}

/* ---------- RISK PANEL ---------- */
export function mapRiskPanel(state: SystemState) {
  return {
    state: state.risk.state ?? "OK",
    violations: state.risk.violations ?? [],
    limits: state.risk.limits ?? {},
  };
}

/* ---------- ACCOUNT PANEL ---------- */
export function mapAccountPanel(state: SystemState) {
  return {
    balance: state.account?.balance ?? null,
    equity: state.account?.equity ?? null,
    marginUsed: state.account?.margin_used ?? null,
  };
}

/* ---------- ANALYTICS PANEL ---------- */
export function mapAnalyticsPanel(state: SystemState) {
  return {
    realizedPnl: state.analytics?.pnl?.realized ?? 0,
    unrealizedPnl: state.analytics?.pnl?.unrealized ?? 0,
    tradeCount: state.analytics?.trade_count ?? 0,
    winRate: state.analytics?.win_rate ?? null,
  };
}

/* ---------- HEALTH PANEL ---------- */
export function mapHealthPanel(state: SystemState) {
  return {
    heartbeatTs: null,
    wsLatencyMs: null,
    components: state.health?.components ?? {},
    isHealthy:
      Object.values(state.health?.components ?? {}).every(
        (v) => v === "OK"
      ),
  };
}

/* ---------- META / WARNINGS ---------- */
export function mapWarnings(state: SystemState) {
  return state.meta?.warnings ?? [];
}
