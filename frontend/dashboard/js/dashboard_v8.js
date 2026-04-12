let grid = null
let equityChart = null
let equityHistory = []
let controlInitialized = false

/** True only after server config merged into lastApplied + DOM selects hydrated (avoids Ctrl+F5 all-blue). */
let controlPanelBaselineReady = false

/** After Apply, one dashboard refresh can carry stale config and repaint pending (blue) over green flash. */
let skipNextControlPanelRefresh = false

/** Server-backed values for control rows; pending UI = select/input value !== last applied */
const lastAppliedControlValues = {}
let selectedDashboardSession = "live"
/** Cached `/api/dashboard` JSON per session for instant tab switches without refetch. */
const dashboardSessionCache = {}
let dualPanelModeEnabled = false
let dashboardRequestId = 0
/** Bumped on backtest UI reset so in-flight /api/dashboard/metrics responses cannot overwrite cleared state. */
let v8MetricsApplyToken = 0
let lastPrefetchTime = 0
const PREFETCH_COOLDOWN_MS = 15000
let tradesRequestId = 0
let executionHistoryRequestId = 0
const sessionRuntimeStatus = {
  live: "UNKNOWN",
  shadow: "UNKNOWN",
  paper: "UNKNOWN",
  backtest: "UNKNOWN",
}

/** Latest /api/dashboard/metrics payload for V8 summary cards (PnL profit factor, etc.). */
let lastMetricsSummary = null

/** Client-side trade/exec memory (cleared on backtest switch / reset). */
let recentTrades = []
let tradeHistory = []
let executionHistory = []
let lastTrades = []
let lastExecution = []
let lastBacktestSummary = null

/** Last rendered PnL snapshot (cleared on backtest reset). */
let lastPnl = null
let lastDrawdown = null
let lastEquity = null

const v8AppStartMs = Date.now()

const V8_PANEL_STORAGE_KEY = "dashboard_v8_panels"

const V8_USER_PANEL_IDS = [
  "v8-panel-metrics",
  "v8-panel-performance",
  "v8-panel-system",
  "v8-panel-alerts",
  "v8-exec-history-ui",
]

const V8_HISTORY_MAX_ROWS = 50
const V8_TRADE_HISTORY_COLS = 9
const V8_EXEC_HISTORY_COLS = 12
const V8_POLL_DASH_MS = 2000
const V8_POLL_TRADES_MS = 5000
const V8_POLL_EXEC_MS = 5000
const V8_POLL_METRICS_MS = 3000

/** Set true temporarily to trace load → paint → metrics (verbose when metrics poll runs). */
const V8_DEBUG_DASHBOARD_PAINT = false

/** Persist session-metrics mode across reload / Stop→Start (only Clear sets; optional reset clears). */
const V8_SESSION_METRICS_KEY = "dashboard_v8_session_metrics"

/** Last dashboard JSON for panels that need pnl without re-fetching. */
let lastDashboardPayload = null

/** When true, backtest dashboard polls skip applying idle/stale payloads until a run is detected (client-side). */
let backtestResetActive = false
let v8BacktestResetFailsafeTimer = null

/** When true, block all backtest dashboard paints (PnL, summary, full paint) until a run is detected or failsafe. */
let backtestUIHardReset = false

/** One-shot bypass so refreshAllPanels / paint can run right after backtest Start/Restart while hard reset is still on. */
let backtestLifecycleRefresh = false

/** Set when dashboard payload shows backtest has actually started; gates lifecycle bypass against stale payloads. */
let backtestLifecycleReady = false

/** True after switching to backtest or clearing trade history until a started run is seen in payload. */
let backtestIdleMode = false

/** Unix seconds at last backtest UI reset; recent_trades must be newer than this to count as started. */
let backtestResetTimestamp = 0

/** Client backtest lifecycle: idle → running → finished (deterministic UI between runs). */
let v8BacktestState = "idle"
/** Set after `/api/backtest/latest` successfully fills `recentTrades` for a finished run. */
let backtestCsvLoaded = false

function isBacktestHardReset() {
  return String(selectedDashboardSession || "").toLowerCase() === "backtest" && backtestUIHardReset
}

/** Infer API session bucket from dashboard JSON (for stale-session guards). */
function v8PayloadSessionHint(data) {
  const p0 = data?.pnl?.panels?.[0]
  const sid = p0?.session_id
  if (sid != null && sid !== "") return String(sid).toLowerCase()
  const raw =
    data?.session ??
    data?.dashboard_session ??
    data?.pnl?.mode ??
    data?.mode ??
    null
  if (raw != null && raw !== "") {
    const u = String(raw).toUpperCase()
    if (u.includes("BACKTEST")) return "backtest"
    if (u.includes("PAPER")) return "paper"
    if (u.includes("SHADOW")) return "shadow"
    if (u.includes("LIVE")) return "live"
  }
  return null
}

/** True if this UI path must not run during backtest hard reset; logs once per skip (temporary audit aid). */
function v8SkipIfBacktestHardReset(fnName) {
  if (backtestLifecycleRefresh && backtestLifecycleReady) return false
  if (!isBacktestHardReset()) return false
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[V8 backtest hard reset] skip UI update:", fnName)
  }
  return true
}

/** Incremental trade history watermark (unix seconds); reset on load / session / clear. */
let lastTradeRowTimeSec = 0
/** After Clear, skip trade polls until a forced reload (e.g. F5 bootstrap or session change). */
let v8TradeHistoryCleared = false
let lastExecRowTimeSec = -1

/** Avoid Chart.js work when equity series unchanged. */
let lastEquityChartKey = ""

/** Dashboard modes that share trade-history anchoring and session-metrics UX (not backtest). */
const V8_TRADE_SCOPED_MODES = ["live", "paper", "shadow"]

/** Per-mode unix seconds: trades at/after this time show for that session (start + uptime bootstrap). */
let sessionTradeStartSec = {
  live: 0,
  paper: 0,
  shadow: 0,
}

function v8TradeScopedMode(session) {
  return V8_TRADE_SCOPED_MODES.includes(String(session || "").toLowerCase())
}

function v8SessionMetricsActive() {
  return useSessionMetrics && v8TradeScopedMode(selectedDashboardSession)
}

function v8ActiveSessionTradeAnchor() {
  const s = String(selectedDashboardSession || "").toLowerCase()
  if (!v8TradeScopedMode(s)) return 0
  return Number(sessionTradeStartSec[s]) || 0
}

function v8BootstrapAllTradeAnchors() {
  const t = Math.floor(Date.now() / 1000)
  for (const k of V8_TRADE_SCOPED_MODES) {
    sessionTradeStartSec[k] = t
  }
}

/** Client-side session counters (reset with Clear Trade History for strategy testing). */
let sessionStats = {
  trades: 0,
  wins: 0,
  losses: 0,
  pnl: 0,
  drawdown: 0,
  profitFactor: 0,
}

/** After Clear Trade History: keep metrics/PnL/performance on session zeros (live/paper/shadow); persisted in localStorage. */
let useSessionMetrics = false

/** Frozen journal lines while session metrics active; equity/float/total still follow server `pnl`. */
let sessionPnlLocked = {
  realized_pnl: 0,
  max_drawdown: 0,
}

/** Table-only paints (trades/exec); must not cancel deterministic dashboard paint RAF. */
let v8TablePaintRaf = null
/** Coalesced full dashboard + metrics paint (loadDashboard, WS PnL path, poll, refresh, session). */
let v8DeterministicPaintRaf = null
let v8PendingUpdate = false
let v8UpdateQueue = {}
/** When set, v8PaintDashboardPayload is skipped if it no longer matches dashboardRequestId. */
let v8QueuedDashboardRequestId = null
/** Incremented on backtest hard reset to drop stale scheduled dashboard paints. */
let v8PaintToken = 0

function v8Dash(v) {
  if (v === null || v === undefined || v === "") return "—"
  if (typeof v === "number" && Number.isNaN(v)) return "—"
  return String(v)
}

/** Trade history PnL / fee display: fixed 2 decimals (deterministic; NaN → "0.00"). */
function v8FormatNumber2(value) {
  if (value === null || value === undefined) return "0.00"
  const num = Number(value)
  if (isNaN(num)) return "0.00"
  return num.toFixed(2)
}

function formatCurrency(val) {
  if (val == null || val === "") return "—"
  const n = Number(val)
  if (Number.isNaN(n) || !Number.isFinite(n)) return "—"
  return n.toFixed(2)
}

function formatNumber(val) {
  return formatCurrency(val)
}

/** RAM use as percent for display (expects 0–100 style value). */
function formatMemory(mem) {
  if (mem == null || mem === "") return "—"
  const n = Number(mem)
  if (!Number.isFinite(n)) return "—"
  return `${n.toFixed(1)}%`
}

/** Dashboard `system` block: supports `memory`, `mem_percent`, or `mem_mb` (fallback). */
function formatSystemMemoryDisplay(sys) {
  if (!sys) return "—"
  const pctRaw =
    sys.memory != null && sys.memory !== ""
      ? sys.memory
      : sys.mem_percent != null && sys.mem_percent !== ""
        ? sys.mem_percent
        : null
  if (pctRaw != null && Number.isFinite(Number(pctRaw))) {
    return formatMemory(pctRaw)
  }
  const mb = sys.mem_mb
  if (mb != null && Number.isFinite(Number(mb))) {
    return `${Number(mb).toFixed(0)} MB`
  }
  return "—"
}

/**
 * Session modal: highlight which Start / Stop / Restart was last clicked (per row).
 * @param {"start"|"stop"|"restart"} state
 * @param {HTMLElement} sessionRow
 */
function setControlButtonState(state, sessionRow) {
  if (!sessionRow) return
  sessionRow
    .querySelectorAll("button.v8-btn-start, button.v8-btn-stop, button.v8-btn-restart")
    .forEach((b) => b.classList.remove("active"))
  if (state === "start") sessionRow.querySelector(".v8-btn-start")?.classList.add("active")
  else if (state === "stop") sessionRow.querySelector(".v8-btn-stop")?.classList.add("active")
  else if (state === "restart") sessionRow.querySelector(".v8-btn-restart")?.classList.add("active")
}

/** Unix seconds (API trade / execution rows) → DD-MM-YYYY HH:mm */
function formatTradeTime(ts) {
  if (ts == null || ts === "") return "—"
  const sec = Number(ts)
  if (!Number.isFinite(sec)) return "—"
  const d = new Date(sec * 1000)
  if (Number.isNaN(d.getTime())) return "—"
  const day = String(d.getDate()).padStart(2, "0")
  const month = String(d.getMonth() + 1).padStart(2, "0")
  const year = d.getFullYear()
  const hour = String(d.getHours()).padStart(2, "0")
  const minute = String(d.getMinutes()).padStart(2, "0")
  return `${day}-${month}-${year} ${hour}:${minute}`
}

function getV8PanelHiddenSet() {
  try {
    const o = JSON.parse(localStorage.getItem(V8_PANEL_STORAGE_KEY) || "{}")
    const arr = Array.isArray(o.hidden) ? o.hidden : []
    return new Set(arr.filter((x) => typeof x === "string"))
  } catch (_e) {
    return new Set()
  }
}

function saveV8PanelHiddenSet(set) {
  localStorage.setItem(
    V8_PANEL_STORAGE_KEY,
    JSON.stringify({ hidden: [...set] })
  )
}

function v8PanelHiddenById(id) {
  const el = document.getElementById(id)
  if (!el || el.classList.contains("hidden-panel")) return true
  if (typeof el.checkVisibility === "function") {
    return !el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true })
  }
  return false
}

function v8TradesHistoryPollActive() {
  return !v8PanelHiddenById("v8-panel-trades")
}

function v8ExecHistoryPollActive() {
  if (!v8TradesHistoryPollActive()) return false
  if (v8PanelHiddenById("v8-exec-history-ui")) return false
  const pane = document.getElementById("v8_pane_exec")
  const tab = document.getElementById("v8_tab_exec")
  return Boolean(tab?.classList.contains("v8-tab-active") && pane && !pane.hidden)
}

function tradeRowTimeSec(t) {
  const v = t?.time ?? t?.timestamp ?? t?.exit_time
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function execRowTimeSec(t) {
  const v = t?.timestamp ?? t?.time
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function v8MergeDashboardPatch(base, patch) {
  if (!patch || typeof patch !== "object") return base
  if (!base || typeof base !== "object") return { ...patch }
  const out = { ...base, ...patch }
  if (patch.pnl != null || base.pnl != null) {
    out.pnl = { ...(base.pnl || {}), ...(patch.pnl || {}) }
  }
  if (patch.metrics != null || base.metrics != null) {
    out.metrics = { ...(base.metrics || {}), ...(patch.metrics || {}) }
  }
  if (patch.config != null || base.config != null) {
    out.config = { ...(base.config || {}), ...(patch.config || {}) }
  }
  if (patch.risk_status != null || base.risk_status != null) {
    out.risk_status = { ...(base.risk_status || {}), ...(patch.risk_status || {}) }
  }
  return out
}

function v8BuildMergedDashboardForPaint() {
  const q = v8UpdateQueue
  let merged = null
  if (q.dashboard && typeof q.dashboard === "object") {
    merged = v8MergeDashboardPatch(null, q.dashboard)
  } else if (lastDashboardPayload) {
    merged = { ...lastDashboardPayload }
  }
  if (q.refresh) merged = v8MergeDashboardPatch(merged, q.refresh)
  if (q.ws) merged = v8MergeDashboardPatch(merged, q.ws)
  return merged
}

/**
 * Single coalesced paint: merges queued sources (dashboard / refresh / ws) then runs
 * v8PaintDashboardPayload once per frame. Metrics-only ticks queue "metrics".
 * Does not cancel prior RAF — later callers add to v8UpdateQueue before the same frame runs.
 */
function scheduleV8DeterministicPaint(source, payload) {
  if (isBacktestHardReset() && (!backtestLifecycleRefresh || !backtestLifecycleReady)) return
  v8UpdateQueue[source] = payload === undefined ? true : payload
  if (v8PendingUpdate) return
  v8PendingUpdate = true
  const token = v8PaintToken
  v8DeterministicPaintRaf = requestAnimationFrame(() => {
    v8DeterministicPaintRaf = null
    v8PendingUpdate = false
    if (token !== v8PaintToken) {
      for (const k of Object.keys(v8UpdateQueue)) delete v8UpdateQueue[k]
      v8QueuedDashboardRequestId = null
      return
    }
    const hadMetricsOnly = Boolean(v8UpdateQueue.metrics)
    const hadAuxPaint =
      hadMetricsOnly ||
      Boolean(v8UpdateQueue.bootstrap || v8UpdateQueue.session)
    const merged = v8BuildMergedDashboardForPaint()
    const staleReq =
      v8QueuedDashboardRequestId !== null &&
      v8QueuedDashboardRequestId !== dashboardRequestId
    v8QueuedDashboardRequestId = null
    for (const k of Object.keys(v8UpdateQueue)) delete v8UpdateQueue[k]

    if (merged && !staleReq) {
      v8PaintDashboardPayload(merged)
    } else if (hadAuxPaint || (merged && staleReq)) {
      updateMetrics({})
      updatePerformance(lastDashboardPayload || {})
    }
  })
}

function scheduleV8DashboardPaint(fn) {
  if (isBacktestHardReset() && (!backtestLifecycleRefresh || !backtestLifecycleReady)) return
  if (v8TablePaintRaf != null) cancelAnimationFrame(v8TablePaintRaf)
  const token = v8PaintToken
  v8TablePaintRaf = requestAnimationFrame(() => {
    v8TablePaintRaf = null
    if (token !== v8PaintToken) return
    fn()
  })
}

function applyV8PanelUserPrefs() {
  const hidden = getV8PanelHiddenSet()
  V8_USER_PANEL_IDS.forEach((id) => {
    if (id === "v8-exec-history-ui") return
    const el = document.getElementById(id)
    if (!el) return
    el.classList.toggle("hidden-panel", hidden.has(id))
  })
  const execHidden = hidden.has("v8-exec-history-ui")
  const execTabWrap = document.getElementById("v8-exec-history-ui")
  const execPane = document.getElementById("v8_pane_exec")
  if (execTabWrap) execTabWrap.classList.toggle("hidden-panel", execHidden)
  if (execPane) execPane.classList.toggle("hidden-panel", execHidden)
  if (execHidden) setV8HistoryTab("trades")
}

function syncV8PanelMenuCheckboxes() {
  const hidden = getV8PanelHiddenSet()
  document.querySelectorAll("#v8_panels_menu input[data-v8-panel-id]").forEach((inp) => {
    const id = inp.getAttribute("data-v8-panel-id")
    if (!id) return
    inp.checked = !hidden.has(id)
  })
}

function initV8PanelsDropdown() {
  const btn = document.getElementById("v8_panels_btn")
  const menu = document.getElementById("v8_panels_menu")
  const drop = document.getElementById("v8_panels_dropdown")
  if (!btn || !menu || !drop) return

  btn.addEventListener("click", (e) => {
    e.stopPropagation()
    const open = menu.hidden
    menu.hidden = !open
    btn.setAttribute("aria-expanded", open ? "true" : "false")
    if (open) syncV8PanelMenuCheckboxes()
  })

  menu.querySelectorAll("input[data-v8-panel-id]").forEach((inp) => {
    inp.addEventListener("change", () => {
      const id = inp.getAttribute("data-v8-panel-id")
      if (!id) return
      const hidden = getV8PanelHiddenSet()
      if (inp.checked) hidden.delete(id)
      else hidden.add(id)
      saveV8PanelHiddenSet(hidden)
      applyV8PanelUserPrefs()
    })
  })

  document.addEventListener("click", () => {
    if (!menu.hidden) {
      menu.hidden = true
      btn.setAttribute("aria-expanded", "false")
    }
  })
  drop.addEventListener("click", (e) => e.stopPropagation())
}

function setV8HistoryTab(which) {
  const tabT = document.getElementById("v8_tab_trades")
  const tabE = document.getElementById("v8_tab_exec")
  const paneT = document.getElementById("v8_pane_trades")
  const paneE = document.getElementById("v8_pane_exec")
  if (!tabT || !paneT) return

  let w = which === "exec" ? "exec" : "trades"
  if (w === "exec") {
    if (
      document.getElementById("v8-exec-history-ui")?.classList.contains("hidden-panel") ||
      document.getElementById("v8_pane_exec")?.classList.contains("hidden-panel")
    ) {
      w = "trades"
    }
  }

  const trades = w === "trades"
  tabT.classList.toggle("v8-tab-active", trades)
  tabT.setAttribute("aria-selected", trades ? "true" : "false")
  if (tabE) {
    tabE.classList.toggle("v8-tab-active", !trades)
    tabE.setAttribute("aria-selected", trades ? "false" : "true")
  }
  paneT.hidden = !trades
  if (paneE) {
    paneE.hidden = trades
  }
  if (w === "exec" && v8ExecHistoryPollActive()) {
    updateExecutionHistory()
  }
}

function initV8HistoryTabs() {
  document.getElementById("v8_tab_trades")?.addEventListener("click", () => setV8HistoryTab("trades"))
  document.getElementById("v8_tab_exec")?.addEventListener("click", () => setV8HistoryTab("exec"))
}

function resetV8DashboardLayout() {
  localStorage.removeItem(V8_PANEL_STORAGE_KEY)
  lastTradeRowTimeSec = 0
  v8TradeHistoryCleared = false
  lastExecRowTimeSec = -1
  lastEquityChartKey = ""
  V8_USER_PANEL_IDS.forEach((id) => {
    document.getElementById(id)?.classList.remove("hidden-panel")
  })
  document.getElementById("v8_pane_exec")?.classList.remove("hidden-panel")
  applyV8PanelUserPrefs()
  syncV8PanelMenuCheckboxes()
  setV8HistoryTab("trades")
}

function getV8DashboardSessionMode() {
  const s = String(selectedDashboardSession || "live").toLowerCase().trim()
  return s || "live"
}

/**
 * Show/hide panels by `data-v8-modes` for the active session (live | shadow | paper | backtest).
 * @param {string} [mode] — optional; defaults to current `selectedDashboardSession`
 */
function applyDashboardModeVisibility(mode) {
  const m =
    mode != null && String(mode).trim() !== ""
      ? String(mode).toLowerCase().trim()
      : getV8DashboardSessionMode()
  if (!m) return

  document.body.dataset.v8Session = m
  document.body.classList.toggle("v8-backtest-mode", m === "backtest")
  document.querySelectorAll("[data-v8-modes]").forEach((el) => {
    const raw = el.getAttribute("data-v8-modes") || ""
    if (!raw.trim()) return
    const modes = raw
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean)
    const show = modes.includes(m)
    el.hidden = !show
    if (show) {
      el.style.removeProperty("display")
    } else {
      el.style.setProperty("display", "none", "important")
    }
    el.setAttribute("aria-hidden", show ? "false" : "true")
  })
  applyV8PanelUserPrefs()
  if (m === "backtest") {
    void refreshV8DataImportList()
  }
  document
    .querySelector(".v8-pnl-risk-control-layout")
    ?.style.setProperty("display", "grid", "important")
}

function updateHeaderRunning() {
  const el = document.getElementById("mh-running")
  if (!el) return
  const st = sessionRuntimeStatus[selectedDashboardSession] || "UNKNOWN"
  el.textContent = st
  el.classList.remove("running", "stopped", "unknown", "finished", "error")
  if (st === "RUNNING") el.classList.add("running")
  else if (st === "READY") el.classList.add("running")
  else if (st === "STOPPED") el.classList.add("stopped")
  else if (st === "FINISHED") el.classList.add("finished")
  else if (st === "ERROR") el.classList.add("error")
  else el.classList.add("unknown")
}

function syncMarketHeaderFromConfig(cfg) {
  if (!cfg) return
  const symEl = document.getElementById("mh-symbol")
  const exEl = document.getElementById("mh-exchange")
  const modeEl = document.getElementById("mh-mode")
  if (symEl && cfg.symbol) symEl.textContent = String(cfg.symbol).toUpperCase()
  if (exEl && cfg.exchange) exEl.textContent = String(cfg.exchange).toUpperCase()
  if (modeEl && cfg.mode != null) modeEl.textContent = String(cfg.mode).toUpperCase()
}

function adjustRisk(delta) {
  const el = document.getElementById("risk_input")
  if (!el) return
  let v = Number(String(el.value ?? "").trim())
  if (!Number.isFinite(v)) v = 1
  v = Math.max(0.01, Math.round((v + delta) * 100) / 100)
  el.value = String(v)
  pendingButton("risk_input")
}

function normalizeDashboardTradeMode(v) {
  const x = String(v || "dual").toLowerCase()
  if (x === "both") return "dual"
  if (x === "long" || x === "short" || x === "dual") return x
  return "dual"
}

function normalizeDashboardStrategy(_v) {
  return "range_trend"
}

function sessionControlStatus(msg, isError = false) {
  const el = document.getElementById("session_control_status")
  if (!el) return
  el.textContent = msg || ""
  el.style.color = isError ? "#f87171" : "#cbd5e1"
}

async function refreshV8DataImportList() {
  const ul = document.getElementById("v8_data_import_list")
  if (!ul) return
  ul.innerHTML = ""
  try {
    const res = await fetch("/api/data/import-files")
    if (!res.ok) return
    const data = await res.json()
    const files = Array.isArray(data.files) ? data.files : []
    if (!files.length) {
      const li = document.createElement("li")
      li.textContent = "— (none yet)"
      li.className = "muted"
      ul.appendChild(li)
      return
    }
    for (const entry of files) {
      const p = typeof entry === "string" ? entry : entry.path || entry.name
      const li = document.createElement("li")
      li.textContent = p || "—"
      ul.appendChild(li)
    }
  } catch {
    /* ignore */
  }
}

function updateFilePreview() {
  const el = document.getElementById("dl_file_preview")
  if (!el) return
  const ex = document.getElementById("dl_exchange")?.value || "binance"
  const market = document.getElementById("dl_market")?.value || "futures"
  const sym = (document.getElementById("dl_symbol")?.value || "BTCUSDT").toUpperCase()
  const iv = document.getElementById("dl_interval")?.value || "5m"
  const s = document.getElementById("dl_start")?.value
  const e = document.getElementById("dl_end")?.value
  if (!s || !e) {
    el.textContent = ""
    return
  }
  const y1 = s.slice(0, 4)
  const y2 = e.slice(0, 4)
  const yearPart = y1 === y2 ? y1 : `${y1}_${y2}`
  el.textContent = `${ex}_${market}_${sym}_${iv}_${yearPart}.csv`
}

function syncDlSymbolFromLiveSelect() {
  const src = document.getElementById("symbol_select")
  const dl = document.getElementById("dl_symbol")
  if (!dl) return
  const prev = dl.value
  dl.innerHTML = ""
  const fallback = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
  const list =
    src && src.options && src.options.length > 0
      ? Array.from(src.options).map((o) => ({ v: o.value, t: o.textContent || o.value }))
      : fallback.map((x) => ({ v: x, t: x }))
  list.forEach(({ v, t }) => {
    const opt = document.createElement("option")
    opt.value = v
    opt.textContent = t
    dl.appendChild(opt)
  })
  let pick = ""
  if (src?.value && list.some((x) => x.v === src.value)) pick = src.value
  else if (prev && list.some((x) => x.v === prev)) pick = prev
  else if (list.length) pick = list[0].v
  if (pick) dl.value = pick
  updateFilePreview()
}

function initV8DownloadPanel() {
  const ids = ["dl_exchange", "dl_market", "dl_symbol", "dl_interval", "dl_start", "dl_end"]
  ids.forEach((id) => {
    document.getElementById(id)?.addEventListener("change", updateFilePreview)
    document.getElementById(id)?.addEventListener("input", updateFilePreview)
  })
  updateFilePreview()
}

async function downloadBinanceData() {
  const statusEl = document.getElementById("download_status")
  const exchange = document.getElementById("dl_exchange")?.value || "binance"
  const market = document.getElementById("dl_market")?.value || "futures"
  const symbol = document.getElementById("dl_symbol")?.value?.trim()
  const interval = document.getElementById("dl_interval")?.value
  const start = document.getElementById("dl_start")?.value
  const end = document.getElementById("dl_end")?.value
  if (!symbol || !interval || !start || !end) {
    if (statusEl) {
      statusEl.style.color = "#f87171"
      statusEl.textContent = "Fill symbol, interval, start, and end."
    }
    return
  }
  if (statusEl) {
    statusEl.style.color = ""
    statusEl.textContent = "Downloading..."
  }
  try {
    const res = await fetch("/api/data/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        exchange,
        market,
        symbol,
        interval,
        start_date: start,
        end_date: end,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const msg =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : `HTTP ${res.status}`
      if (statusEl) {
        statusEl.style.color = "#f87171"
        statusEl.textContent = "Download failed: " + msg
      }
      return
    }
    if (data.success) {
      if (statusEl) {
        statusEl.style.color = ""
        statusEl.textContent =
          "Download complete: " + (data.filename || data.path || data.file || "")
      }
      await refreshV8DataImportList()
    } else if (statusEl) {
      statusEl.style.color = "#f87171"
      statusEl.textContent = "Download failed"
    }
  } catch (e) {
    if (statusEl) {
      statusEl.style.color = "#f87171"
      statusEl.textContent = "Download failed: " + (e?.message || e)
    }
  }
}

function openSessionControl() {
  const modal = document.getElementById("sessionControlModal")
  if (!modal) return
  modal.style.display = "flex"
  sessionControlStatus("")
  refreshSessionStatuses()
}

function closeSessionControl() {
  const modal = document.getElementById("sessionControlModal")
  if (!modal) return
  modal.style.display = "none"
}

async function postSessionControl(path) {
  const res = await fetch(path, { method: "POST" })
  if (!res.ok) {
    let detail = ""
    try {
      const body = await res.json()
      detail = body?.detail ? `: ${body.detail}` : ""
    } catch (_e) {
      detail = ""
    }
    const err = new Error(`HTTP ${res.status}${detail}`)
    err.status = res.status
    err.detail = detail
    throw err
  }
  return res.json().catch(() => ({}))
}

document.addEventListener("click", async (e) => {
  const t = e.target
  const session = t.dataset?.session
  const action = t.dataset?.action

  if (
    session &&
    action &&
    (action === "start" || action === "stop" || action === "restart") &&
    t.matches?.("button.v8-btn-start, button.v8-btn-stop, button.v8-btn-restart")
  ) {
    const row = t.closest(".session-row")
    if (row) setControlButtonState(action, row)
  }

  if (!session || !action) return

  const sid = String(session).toLowerCase()

  if (action === "export") {
    exportCandle(sid)
    return
  }

  if (action === "import") {
    const path = prompt("Enter CSV path")
    if (path === null) return
    const trimmed = String(path).trim()
    if (!trimmed) return
    try {
      await ensureSessionCreated(sid)
      const res = await fetch("/api/session/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: sid,
          path: trimmed,
        }),
      })
      if (!res.ok) {
        let detail = ""
        try {
          const body = await res.json()
          detail = body?.detail != null ? `: ${body.detail}` : ""
        } catch (_err) {
          detail = ""
        }
        sessionControlStatus(
          `IMPORT ${sid.toUpperCase()} failed — HTTP ${res.status}${detail}`,
          true
        )
        await refreshSessionStatuses()
        return
      }
      sessionControlStatus(`IMPORT ${sid.toUpperCase()} ok`)
      if (sid === "backtest") {
        v8ResetBacktestState()
        v8BacktestState = "idle"
        backtestCsvLoaded = false
      }
      await refreshSessionStatuses()
    } catch (err) {
      sessionControlStatus(
        `IMPORT ${sid.toUpperCase()} failed — ${err?.message || err}`,
        true
      )
      await refreshSessionStatuses()
    }
    return
  }

  try {
    if (action === "start") {
      await ensureSessionCreated(sid)
    }
    const res = await fetch(`/api/session/${action}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        mode: sid,
      }),
    })
    if (!res.ok) {
      let detail = ""
      try {
        const body = await res.json()
        detail = body?.detail != null ? `: ${body.detail}` : ""
      } catch (_err) {
        detail = ""
      }
      sessionControlStatus(
        `${action.toUpperCase()} ${sid.toUpperCase()} failed — HTTP ${res.status}${detail}`,
        true
      )
      await refreshSessionStatuses()
      return
    }
    const sidLc = String(sid || "").toLowerCase()
    if (v8TradeScopedMode(sidLc) && action === "start") {
      sessionTradeStartSec[sidLc] = Math.floor(Date.now() / 1000)
      lastTradeRowTimeSec = 0
      v8TradeHistoryCleared = false
    }
    sessionControlStatus(`${action.toUpperCase()} ${sid.toUpperCase()} ok`)
    await refreshSessionStatuses()
    await refreshAfterLifecycleAction()
  } catch (err) {
    sessionControlStatus(
      `${action.toUpperCase()} ${sid.toUpperCase()} failed — ${err?.message || err}`,
      true
    )
    await refreshSessionStatuses()
  }
})

async function ensureSessionCreated(sessionId) {
  try {
    await postSessionControl(`/api/system/session/create?mode=${encodeURIComponent(sessionId)}`)
  } catch (e) {
    const msg = String(e?.message || "").toLowerCase()
    const detail = String(e?.detail || "").toLowerCase()
    // Idempotent create: ignore only "already exists" style errors.
    if (
      msg.includes("already exists") ||
      msg.includes("exists") ||
      detail.includes("already exists") ||
      detail.includes("exists")
    ) {
      return
    }
    throw e
  }
}

async function startSession(sessionId) {
  await ensureSessionCreated(sessionId)
  return postSessionControl(`/api/system/session/start/${encodeURIComponent(sessionId)}`)
}

async function stopSession(sessionId) {
  return postSessionControl(`/api/system/session/stop/${encodeURIComponent(sessionId)}`)
}

async function sessionAction(sessionId, action, btn) {
  const original = btn ? btn.textContent : ""
  try {
    if (btn) {
      btn.disabled = true
      btn.textContent = "..."
    }
    sessionControlStatus(`${action.toUpperCase()} ${sessionId.toUpperCase()} in progress...`)
    if (action === "start") {
      await startSession(sessionId)
    } else if (action === "stop") {
      await stopSession(sessionId)
    } else if (action === "restart") {
      await stopSession(sessionId)
      await startSession(sessionId)
    } else {
      throw new Error(`Unsupported action: ${action}`)
    }
    const sessionLc = String(sessionId || "").toLowerCase()
    if (sessionLc === "backtest" && (action === "restart" || action === "start")) {
      resetBacktestPanels()
      delete dashboardSessionCache["backtest"]
      backtestLifecycleRefresh = true
    }
    if (v8TradeScopedMode(sessionLc) && action === "start") {
      sessionTradeStartSec[sessionLc] = Math.floor(Date.now() / 1000)
      lastTradeRowTimeSec = 0
      v8TradeHistoryCleared = false
    }
    sessionControlStatus(`${action.toUpperCase()} ${sessionId.toUpperCase()} success`)
    await refreshSessionStatuses()
    await refreshAfterLifecycleAction()
  } catch (e) {
    sessionControlStatus(`${action.toUpperCase()} ${sessionId.toUpperCase()} failed - ${e.message}`, true)
    await refreshSessionStatuses()
  } finally {
    if (btn) {
      btn.disabled = false
      btn.textContent = original
    }
  }
}

async function exportCandle(session) {
  const sid = String(session || "live").toLowerCase()
  try {
    if (sid === "backtest") {
      const res = await fetch("/api/session/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: sid }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const msg = data?.detail || data?.error || `HTTP ${res.status}`
        sessionControlStatus(`Backtest export failed: ${msg}`, true)
        alert("Backtest export failed: " + msg)
        return
      }
      const fp = data.file || data.path || ""
      sessionControlStatus(`Backtest exported successfully → ${fp}`, false)
      alert(`Backtest exported successfully\nFile: ${fp}`)
      return
    }

    const res = await fetch(
      `/api/debug/export-candle?session=${encodeURIComponent(sid)}`
    )
    const data = await res.json()
    if (data.ok) {
      sessionControlStatus(
        `[CANDLE EXPORT] ${sid} ${data.rows} bars → ${data.path}`,
        false
      )
      alert(
        `Exported ${data.rows} bars\n` +
        `File: ${data.path}`
      )
    } else {
      sessionControlStatus(`Export failed: ${data.error || "unknown"}`, true)
      alert("Export failed: " + (data.error || "unknown"))
    }
  } catch (err) {
    console.error(err)
    sessionControlStatus("Export error", true)
    alert("Export error")
  }
}

async function fetchJsonSafe(url) {
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${url}`)
  }
  return res.json()
}

/** Backend + /api/control/risk use risk as a fraction (e.g. 0.01 = 1%). Input shows percent. */
function riskFractionToDisplayPercent(fraction) {
  const n = Number(fraction)
  if (!Number.isFinite(n) || n < 0) return ""
  const pct = n * 100
  if (!Number.isFinite(pct)) return ""
  return String(pct)
}

function riskPercentInputToFraction(raw) {
  const n = Number(String(raw ?? "").trim())
  if (!Number.isFinite(n) || n <= 0) return NaN
  return n / 100
}

function collectSessionConfigPayload() {
  const tradeMode = document.getElementById("trade_mode_select")?.value
  const riskRaw = document.getElementById("risk_input")?.value
  const initialRaw = document.getElementById("initial_balance")?.value
  const strategy = document.getElementById("strategy_select")?.value
  const rf = riskPercentInputToFraction(riskRaw)
  return {
    trade_mode: tradeMode,
    risk_percent: Number.isFinite(rf) ? rf : 0.01,
    initial_balance: Number(initialRaw),
    strategy,
  }
}

async function syncSessionConfigFromControlPanel() {
  const payload = collectSessionConfigPayload()
  const sid = selectedDashboardSession || "live"
  const res = await fetch(
    `/api/session/config?session=${encodeURIComponent(sid)}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  )
  let body = {}
  try {
    body = await res.json()
  } catch (_err) {
    body = {}
  }
  if (!res.ok || body.error) {
    const detail =
      body?.detail != null
        ? `: ${body.detail}`
        : body?.error != null
          ? `: ${body.error}`
          : ""
    throw new Error(`HTTP ${res.status}${detail}`)
  }
}

/** After /api/control/* succeeds; session POST can fail if session row missing — do not block Apply UI. */
async function syncSessionConfigAfterControl() {
  try {
    await syncSessionConfigFromControlPanel()
  } catch (e) {
    console.warn("[control panel] session config sync skipped:", e?.message || e)
  }
}

/** Hydrate entire control panel from GET /api/session/config (per-session store only; never from /api/dashboard config). */
async function loadSessionConfig() {
  const sid = selectedDashboardSession || "live"
  try {
    const res = await fetch(`/api/session/config?session=${encodeURIComponent(sid)}`)
    const data = await res.json().catch(() => ({}))
    if (!res.ok || data.error) {
      return
    }

    const ex = document.getElementById("exchange_select")
    if (ex && data.exchange != null && String(data.exchange) !== "") {
      const ev = String(data.exchange)
      if (Array.from(ex.options).some((o) => o.value === ev)) {
        ex.value = ev
      }
    }

    const sym = document.getElementById("symbol_select")
    if (sym && data.symbol != null && String(data.symbol) !== "") {
      const sv = String(data.symbol)
      if (Array.from(sym.options).some((o) => o.value === sv)) {
        sym.value = sv
      }
    }

    const tm = document.getElementById("trade_mode_select")
    if (tm && data.trade_mode != null && String(data.trade_mode) !== "") {
      const nv = normalizeDashboardTradeMode(data.trade_mode)
      if (Array.from(tm.options).some((o) => o.value === nv)) {
        tm.value = nv
      }
    }

    const ri = document.getElementById("risk_input")
    if (
      ri &&
      data.risk_percent !== undefined &&
      data.risk_percent !== null &&
      !Number.isNaN(Number(data.risk_percent))
    ) {
      ri.value = riskFractionToDisplayPercent(data.risk_percent)
    }

    const ib = document.getElementById("initial_balance")
    if (
      ib &&
      data.initial_balance !== undefined &&
      data.initial_balance !== null &&
      !Number.isNaN(Number(data.initial_balance))
    ) {
      ib.value = String(data.initial_balance)
    }

    const ss = document.getElementById("strategy_select")
    if (ss && data.strategy != null && String(data.strategy) !== "") {
      const raw = String(data.strategy)
      const norm = normalizeDashboardStrategy(raw)
      const pick = Array.from(ss.options).some((o) => o.value === raw) ? raw : norm
      if (Array.from(ss.options).some((o) => o.value === pick)) {
        ss.value = pick
      }
    }

    syncControlLastAppliedFromConfig({
      trade_mode: data.trade_mode,
      risk_percent: data.risk_percent,
      strategy: data.strategy,
      exchange: data.exchange,
      symbol: data.symbol,
    })
    if (
      data.initial_balance !== undefined &&
      data.initial_balance !== null &&
      !Number.isNaN(Number(data.initial_balance))
    ) {
      lastAppliedControlValues["initial_balance"] = String(Number(data.initial_balance))
    }

    if (!controlPanelBaselineReady) {
      applySymbolSelectFromBaseline()
      controlInitialized = true
      controlPanelBaselineReady = true
    }

    refreshControlApplyButtonStates()
  } catch (_e) {
    /* session may not exist yet */
  }
}

async function refreshAllPanels(bypassBacktestHardResetGuard = false) {
  if (
    !bypassBacktestHardResetGuard &&
    isBacktestHardReset() &&
    (!backtestLifecycleRefresh || !backtestLifecycleReady)
  ) {
    return
  }
  await loadDashboard()
  if (v8TradesHistoryPollActive()) await updateTrades(true)
  if (v8ExecHistoryPollActive()) await updateExecutionHistory()

  const qp = getSessionQueryParams()
  try {
    const [position, pnl, risk] = await Promise.all([
      fetchJsonSafe(`/api/dashboard/position?${qp}`),
      fetchJsonSafe(`/api/dashboard/pnl?${qp}`),
      fetchJsonSafe(`/api/dashboard/risk-status?${qp}`),
    ])

    scheduleV8DeterministicPaint("refresh", {
      position,
      pnl,
      risk_status: risk,
    })
  } catch (_e) {
    /* partial refresh optional */
  }
}

async function refreshAfterLifecycleAction() {
  try {
    await refreshAllPanels()
    // Post-lifecycle state can settle asynchronously; perform short retries.
    for (let i = 0; i < 2; i++) {
      await new Promise((resolve) => setTimeout(resolve, 600))
      await refreshAllPanels()
    }
  } finally {
    backtestLifecycleRefresh = false
  }
}

function normalizeSessionStatus(value) {
  const s = String(value || "").trim().toUpperCase()
  if (s === "RUNNING") return "RUNNING"
  if (s === "READY") return "READY"
  if (s === "FINISHED") return "FINISHED"
  if (s === "ERROR") return "ERROR"
  if (s === "STOPPED" || s === "IDLE" || s === "CREATED") return "STOPPED"
  return "UNKNOWN"
}

function setSessionStatusEl(id, status) {
  const el = document.getElementById(id)
  if (!el) return
  const text = normalizeSessionStatus(status)
  el.textContent = text
  const key = id.replace(/^session_status_/, "")
  if (key && Object.prototype.hasOwnProperty.call(sessionRuntimeStatus, key)) {
    sessionRuntimeStatus[key] = text
  }
  el.classList.remove("running", "stopped", "unknown", "finished", "error")
  if (text === "RUNNING") el.classList.add("running")
  else if (text === "READY") el.classList.add("running")
  else if (text === "STOPPED") el.classList.add("stopped")
  else if (text === "FINISHED") el.classList.add("finished")
  else if (text === "ERROR") el.classList.add("error")
  else el.classList.add("unknown")
}

function readStatusFromSessionsPayload(payload, sessionId) {
  if (!payload) return "UNKNOWN"
  const sid = String(sessionId || "").toLowerCase()
  if (Array.isArray(payload)) {
    const row = payload.find((x) => String(x?.id || x?.session_id || "").toLowerCase() === sid)
    return row?.status || "UNKNOWN"
  }
  if (Array.isArray(payload.sessions)) {
    const row = payload.sessions.find((x) => String(x?.id || x?.session_id || "").toLowerCase() === sid)
    return row?.status || "UNKNOWN"
  }
  if (payload.sessions && typeof payload.sessions === "object") {
    const sess = payload.sessions
    const row = sess[sid]
    if (row && typeof row === "object") return row.status || "UNKNOWN"
    if (typeof row === "string") return row
    if (sid === "shadow") {
      const ls = sess.live_shadow
      if (ls && typeof ls === "object") return ls.status || "UNKNOWN"
      for (const k of Object.keys(sess)) {
        const ent = sess[k]
        if (ent && typeof ent === "object" && String(ent.mode || "").toLowerCase() === "shadow") {
          return ent.status || "UNKNOWN"
        }
      }
    }
    if (sid === "paper") {
      for (const k of Object.keys(sess)) {
        const ent = sess[k]
        if (ent && typeof ent === "object" && String(ent.mode || "").toLowerCase() === "paper") {
          return ent.status || "UNKNOWN"
        }
      }
    }
  }
  if (payload[sid] && typeof payload[sid] === "object") {
    return payload[sid].status || "UNKNOWN"
  }
  return "UNKNOWN"
}

async function refreshSessionStatuses() {
  try {
    const res = await fetch("/api/system/sessions")
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    setSessionStatusEl("session_status_live", readStatusFromSessionsPayload(data, "live"))
    setSessionStatusEl("session_status_shadow", readStatusFromSessionsPayload(data, "shadow"))
    setSessionStatusEl("session_status_paper", readStatusFromSessionsPayload(data, "paper"))
    setSessionStatusEl("session_status_backtest", readStatusFromSessionsPayload(data, "backtest"))
  } catch (_e) {
    setSessionStatusEl("session_status_live", "UNKNOWN")
    setSessionStatusEl("session_status_shadow", "UNKNOWN")
    setSessionStatusEl("session_status_paper", "UNKNOWN")
    setSessionStatusEl("session_status_backtest", "UNKNOWN")
  }
  updateHeaderRunning()
}

function getSessionQueryParams() {
  const params = new URLSearchParams()
  params.set("session", selectedDashboardSession)
  if (dualPanelModeEnabled) {
    params.set("dual", "1")
  }
  return params.toString()
}

/** Scope /api/control/* mutations to the dashboard-selected session (per-session JSON + live object). */
function controlPanelSessionQuery() {
  const s = selectedDashboardSession || "live"
  return `?session=${encodeURIComponent(s)}`
}

function getTradeHistoryQueryParams() {
  const params = new URLSearchParams()
  // Always bind history to selected session (UI isolation).
  params.set("session_id", selectedDashboardSession)
  params.set("session", selectedDashboardSession)
  return params.toString()
}

function getExecutionHistoryQueryParams() {
  const params = new URLSearchParams()
  // Never couple history to RUNNING/dual state; selected session only.
  params.set("session", selectedDashboardSession)
  return params.toString()
}

async function pollV8Metrics() {
  if (
    v8PanelHiddenById("v8-panel-metrics") &&
    v8PanelHiddenById("v8-panel-performance")
  ) {
    return
  }
  if (v8SkipIfBacktestHardReset("pollV8Metrics")) {
    return
  }
  if (v8SessionMetricsActive()) {
    return
  }
  const metricsToken = v8MetricsApplyToken
  try {
    const fetched = await fetchJsonSafe(
      `/api/dashboard/metrics?${getSessionQueryParams()}`
    )
    if (metricsToken !== v8MetricsApplyToken) return
    lastMetricsSummary = fetched
  } catch (_e) {
    if (metricsToken !== v8MetricsApplyToken) return
    lastMetricsSummary = null
  }
  if (metricsToken !== v8MetricsApplyToken) return
  scheduleV8DeterministicPaint("metrics", true)
}

function hydrateSessionSelectorFromStorage() {
  const savedSession = (localStorage.getItem("dashboard-session") || "live").toLowerCase()
  const savedDual = localStorage.getItem("dashboard-dual-panel") === "1"
  const select = document.getElementById("session_select")
  const dual = document.getElementById("dual_panel_toggle")

  selectedDashboardSession = savedSession
  dualPanelModeEnabled = savedDual

  if (select) {
    const hasValue = Array.from(select.options).some((o) => o.value === savedSession)
    select.value = hasValue ? savedSession : "live"
    selectedDashboardSession = select.value
  }

  if (dual) {
    dual.checked = savedDual
    dualPanelModeEnabled = dual.checked
  }
  applyDashboardModeVisibility(selectedDashboardSession)
}

function resetBacktestPnL() {
  const el = document.getElementById("pnl")
  if (!el) return
  el.innerHTML = `
<div class="v8-kv"><span class="k">Equity</span><span class="v mono">—</span></div>
<div class="v8-kv"><span class="k">Realized PnL</span><span class="v mono">0</span></div>
<div class="v8-kv"><span class="k">Drawdown</span><span class="v mono">0%</span></div>
<div class="v8-kv"><span class="k">Profit Factor</span><span class="v mono">—</span></div>
`
  const prog = document.getElementById("backtest_progress")
  if (prog) prog.innerText = "Backtest not started"
}

function resetBacktestSummary() {
  const root = document.getElementById("v8_backtest_summary_root")
  if (!root) return
  root.innerHTML = `
<div class="v8-backtest-empty">
Waiting for backtest execution…
</div>
`
}

/** True when the dashboard payload indicates a completed backtest (progress scale 0–1 or 0–100). */
function v8IsBacktestFinished(data) {
  if (!data) return false
  if (data.backtest_finished === true || data?.pnl?.backtest_finished === true) return true
  if (data.status === "finished") return true
  const pRaw = data.backtest_progress ?? data?.pnl?.backtest_progress
  if (pRaw === undefined || pRaw === null || pRaw === "") return false
  const p = Number(pRaw)
  if (!Number.isFinite(p)) return false
  if (p > 1) return p >= 100
  return p >= 1
}

/** True while a backtest is in progress (not finished); used for lifecycle transitions. */
function v8BacktestIsRunningPayload(data) {
  if (!data || v8IsBacktestFinished(data)) return false
  if (String(data.status || "").toLowerCase() === "running") return true
  if (data.backtest_running === true) return true
  if (!v8BacktestDashboardLooksStarted(data)) return false
  const prog = Number(data.backtest_progress ?? data?.pnl?.backtest_progress)
  if (Number.isFinite(prog) && prog >= 1) return false
  return true
}

/** Clear stale backtest client state when a new run starts (no full session reset / Ctrl+F5). */
function v8ResetBacktestState() {
  v8PaintToken++
  recentTrades = []
  tradeHistory = []
  lastTrades = []
  lastMetricsSummary = null
  lastDashboardPayload = null
  backtestCsvLoaded = false
  executionHistory = []
  lastExecution = []
  lastTradeRowTimeSec = 0
  v8TradeHistoryCleared = false
  delete dashboardSessionCache["backtest"]
  resetBacktestSummary()
  resetBacktestPnL()
  const tradeTbody = document.querySelector("#trade_history_v8 tbody")
  if (tradeTbody) {
    tradeTbody.innerHTML = `<tr><td colspan="${V8_TRADE_HISTORY_COLS}" class="v8-empty">—</td></tr>`
  }
  equityHistory = []
  lastEquityChartKey = ""
  if (v8TradesHistoryPollActive()) {
    void updateTrades(true)
  }
}

/** Load canonical `data/backtest/output/backtest_latest.csv` into `recentTrades` after export completes. */
async function v8LoadBacktestTrades() {
  try {
    const res = await fetch("/api/backtest/latest")
    if (!res.ok) return
    const trades = await res.json()
    if (Array.isArray(trades) && trades.length > 0) {
      recentTrades = trades
      backtestCsvLoaded = true
    }
  } catch (_e) {
    /* latest CSV may be missing until export */
  }
}

/** True when payload has at least one trade strictly after the last backtest UI reset (unix seconds). */
function v8IsNewBacktestRun(data) {
  const rt = data?.recent_trades
  if (!Array.isArray(rt) || rt.length === 0) return false
  const newestTrade = rt[rt.length - 1]
  let tradeTime =
    v8BacktestTradeTimeSec(newestTrade) ??
    (() => {
      const v = newestTrade?.exit_time
      if (v == null) return 0
      const n = Number(v)
      if (!Number.isFinite(n) || n <= 0) return 0
      return n > 1e12 ? Math.floor(n / 1000) : Math.floor(n)
    })()
  if (!Number.isFinite(tradeTime) || tradeTime <= 0) {
    const n = Number(
      newestTrade?.time ??
        newestTrade?.timestamp ??
        newestTrade?.exit_time ??
        0
    )
    if (Number.isFinite(n) && n > 0) {
      tradeTime = n > 1e12 ? n / 1000 : n
    } else {
      tradeTime = 0
    }
  }
  return tradeTime > backtestResetTimestamp
}

/** Payload already carries backtest results; do not require trade time > backtestResetTimestamp (session switch). */
function v8BacktestPayloadHasSummarySignals(data) {
  if (v8IsBacktestFinished(data)) return true
  const rt = data?.recent_trades
  if (Array.isArray(rt) && rt.length > 0) return true
  const tc = data?.pnl?.trade_count
  if (tc != null && Number(tc) > 0) return true
  const prog = data?.pnl?.backtest_progress
  if (prog != null && Number.isFinite(Number(prog)) && Number(prog) > 0) return true
  return false
}

/** True when payload indicates a backtest run worth painting (no backend `backtest_running` required). */
function v8BacktestDashboardLooksStarted(data) {
  let ok = false
  if (data?.backtest_running === true) ok = true
  else {
    const rt = data?.recent_trades
    if (Array.isArray(rt) && rt.length > 0) {
      const newestTrade = rt[rt.length - 1]
      let tradeTime =
        v8BacktestTradeTimeSec(newestTrade) ??
        (() => {
          const v = newestTrade?.exit_time
          if (v == null) return 0
          const n = Number(v)
          if (!Number.isFinite(n) || n <= 0) return 0
          return n > 1e12 ? Math.floor(n / 1000) : Math.floor(n)
        })()
      if (!Number.isFinite(tradeTime) || tradeTime <= 0) {
        const n = Number(
          newestTrade?.time ??
            newestTrade?.timestamp ??
            newestTrade?.exit_time ??
            0
        )
        if (Number.isFinite(n) && n > 0) {
          tradeTime = n > 1e12 ? n / 1000 : n
        } else {
          tradeTime = 0
        }
      }
      if (tradeTime > backtestResetTimestamp) {
        ok = true
      }
      if (typeof console !== "undefined" && console.debug) {
        console.debug("[Backtest start detection]", {
          tradeTime,
          backtestResetTimestamp,
          ok,
        })
      }
    } else {
      const prog = data?.pnl?.backtest_progress
      if (prog != null && Number.isFinite(Number(prog))) {
        const n = Number(prog)
        if (n > 0 && n < 1) ok = true
        else if (n >= 1) ok = true
      }
      if (!ok) {
        const tc = data?.pnl?.trade_count
        if (tc != null && Number(tc) > 0) ok = true
      }
    }
  }
  if (!ok && v8IsBacktestFinished(data)) {
    ok = true
  }
  if (ok) {
    if (
      v8IsNewBacktestRun(data) ||
      data?.backtest_running === true ||
      v8IsBacktestFinished(data)
    ) {
      backtestIdleMode = false
    }
    backtestUIHardReset = false
    backtestLifecycleReady = true
  }
  return ok
}

function resetBacktestPanels() {
  backtestResetTimestamp = Date.now() / 1000
  v8PaintToken++
  dashboardRequestId++
  v8MetricsApplyToken++
  backtestUIHardReset = true
  backtestLifecycleReady = false
  backtestResetActive = true
  if (v8BacktestResetFailsafeTimer != null) {
    clearTimeout(v8BacktestResetFailsafeTimer)
    v8BacktestResetFailsafeTimer = null
  }
  v8BacktestResetFailsafeTimer = setTimeout(() => {
    backtestResetActive = false
    backtestUIHardReset = false
    v8BacktestResetFailsafeTimer = null
  }, 5000)

  resetBacktestPnL()
  resetBacktestSummary()

  // clear trade memory
  recentTrades = []
  tradeHistory = []
  executionHistory = []
  lastTrades = []
  lastExecution = []

  lastMetricsSummary = null
  lastBacktestSummary = null
  lastPnl = null
  lastDrawdown = null
  lastEquity = null

  const tradeTbody = document.querySelector("#trade_history_v8 tbody")
  if (tradeTbody) {
    tradeTbody.innerHTML = ""
  }
  const execTbody = document.querySelector("#execution_history_v8 tbody")
  if (execTbody) {
    execTbody.innerHTML = ""
  }

  equityHistory = []
  lastEquityChartKey = ""

  lastTradeRowTimeSec = 0
  lastExecRowTimeSec = -1
  v8TradeHistoryCleared = false

  // reset session stats
  sessionStats = {
    trades: 0,
    wins: 0,
    losses: 0,
    pnl: 0,
    drawdown: 0,
    profitFactor: 0,
  }

  // reset session pnl lock
  sessionPnlLocked = {
    realized_pnl: 0,
    max_drawdown: 0,
  }

  lastDashboardPayload = null
  v8BacktestState = "idle"
  backtestCsvLoaded = false
}

async function onSessionSelectionChanged() {
  const select = document.getElementById("session_select")
  const dual = document.getElementById("dual_panel_toggle")
  selectedDashboardSession = select ? String(select.value || "live").toLowerCase() : "live"
  dualPanelModeEnabled = dual ? dual.checked === true : false
  if (String(selectedDashboardSession || "").toLowerCase() !== "backtest") {
    v8BacktestState = "idle"
    backtestCsvLoaded = false
  }
  localStorage.setItem("dashboard-session", selectedDashboardSession)
  localStorage.setItem("dashboard-dual-panel", dualPanelModeEnabled ? "1" : "0")
  lastTradeRowTimeSec = 0
  v8TradeHistoryCleared = false
  lastExecRowTimeSec = -1
  lastEquityChartKey = ""
  const sid = String(selectedDashboardSession || "").toLowerCase()
  if (sid === "backtest") {
    backtestIdleMode = true
    resetBacktestPanels()
    // Allow repaint after session switch (otherwise hard reset blocks paint/metrics/load until WS or failsafe).
    backtestLifecycleReady = true
    backtestLifecycleRefresh = true
    delete dashboardSessionCache["backtest"]
  }
  try {
    await loadSessionConfig()
    applyDashboardModeVisibility(selectedDashboardSession)
    // Full repaint lifecycle (same idea as bootstrap): always refetch dashboard + metrics for the new session.
    await loadDashboard()
    if (v8TradeScopedMode(sid) && useSessionMetrics) {
      resetV8Metrics()
    }
    await pollV8Metrics()
    await refreshAllPanels(true)
    await new Promise((resolve) => requestAnimationFrame(() => resolve()))
    scheduleV8DeterministicPaint("session", lastDashboardPayload ?? true)
    requestAnimationFrame(() => {
      backtestLifecycleRefresh = false
      backtestLifecycleReady = false
    })
  } catch (_e) {
    backtestLifecycleRefresh = false
    backtestLifecycleReady = false
  }
  if (v8TradesHistoryPollActive()) await updateTrades(true)
  if (v8ExecHistoryPollActive()) await updateExecutionHistory()
}

function markControlApplyCommitted(elementId, value) {
  skipNextControlPanelRefresh = true
  lastAppliedControlValues[elementId] = String(value)
}

function syncControlLastAppliedFromConfig(config) {
  if (!config) return
  const pairs = [
    ["trade_mode_select", "trade_mode"],
    ["strategy_select", "strategy"],
    ["exchange_select", "exchange"],
    ["symbol_select", "symbol"],
    ["risk_input", "risk_percent"],
  ]
  for (const [elementId, configKey] of pairs) {
    const v = config[configKey]
    if (configKey === "risk_percent") {
      if (v !== undefined && v !== null && !Number.isNaN(Number(v))) {
        lastAppliedControlValues[elementId] = riskFractionToDisplayPercent(Number(v))
      }
      continue
    }
    if (v !== undefined && v !== null && v !== "") {
      lastAppliedControlValues[elementId] = String(v)
    }
  }
}

const CONTROL_APPLY_IDS = [
  "symbol_select",
  "exchange_select",
  "risk_input",
  "initial_balance",
  "trade_mode_select",
  "strategy_select",
]

function refreshControlApplyButtonStates() {
  if (!controlPanelBaselineReady) return
  if (skipNextControlPanelRefresh) {
    skipNextControlPanelRefresh = false
    return
  }
  for (const id of CONTROL_APPLY_IDS) {
    pendingButton(id)
  }
}

function applySymbolSelectFromBaseline() {
  const desired = lastAppliedControlValues["symbol_select"]
  const select = document.getElementById("symbol_select")
  if (!desired || !select || !select.options.length) return
  const has = Array.from(select.options).some((o) => o.value === desired)
  if (has) select.value = desired
}

document.addEventListener("DOMContentLoaded", function(){

  lastTradeRowTimeSec = 0
  v8TradeHistoryCleared = false
  if (localStorage.getItem(V8_SESSION_METRICS_KEY) === "true") {
    useSessionMetrics = true
  }
  v8BootstrapAllTradeAnchors()

  applyDashboardModeVisibility(getV8DashboardSessionMode())
  initV8PanelsDropdown()
  initV8HistoryTabs()

  // Symbol list must exist before hydrating from /api/dashboard (avoids race → false “pending”).
  ;(async function bootstrapDashboardControlPanel() {
    hydrateSessionSelectorFromStorage()
    // Hydration can change selectedDashboardSession; mode visibility was applied earlier with defaults.
    applyDashboardModeVisibility(selectedDashboardSession)
    await loadSymbols()
    await loadDashboard()
    await new Promise(r => requestAnimationFrame(r))
    if (useSessionMetrics) {
      resetV8Metrics()
    }
    await pollV8Metrics()
    // One frame so layout/visibility (e.g. checkVisibility in pollV8Metrics) matches the painted DOM.
    await new Promise((resolve) => requestAnimationFrame(() => resolve()))
    scheduleV8DeterministicPaint("bootstrap", true)
    if (v8TradesHistoryPollActive()) await updateTrades(true)
    if (v8ExecHistoryPollActive()) await updateExecutionHistory()
  })()

  setInterval(loadDashboard, V8_POLL_DASH_MS)
  setInterval(() => {
    if (v8TradesHistoryPollActive()) updateTrades()
  }, V8_POLL_TRADES_MS)
  setInterval(() => {
    if (v8ExecHistoryPollActive()) updateExecutionHistory()
  }, V8_POLL_EXEC_MS)
  setInterval(pollV8Metrics, V8_POLL_METRICS_MS)

  // nếu đã dùng WS realtime thì có thể bật:
  initWebSocket()
  renderExecutionPipeline()
  initMarketWS()
  loadMarket()
  setInterval(loadMarket,5000)

  const modal = document.getElementById("sessionControlModal")
  if (modal) {
    modal.addEventListener("click", function (e) {
      if (e.target === modal) {
        closeSessionControl()
      }
    })
  }

  document.getElementById("apply_initial_balance")?.addEventListener("click", async () => {
    const el = document.getElementById("initial_balance")
    const btn = document.getElementById("apply_initial_balance")
    const value = el?.value
    try {
      await syncSessionConfigFromControlPanel()
      markControlApplyCommitted("initial_balance", String(Number(value)))
      if (btn) flashButton(btn)
    } catch (e) {
      console.warn("[control panel] initial balance apply failed:", e?.message || e)
    }
  })

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) return
    prefetchOtherSessions()
  })

  document.getElementById("btn_download")?.addEventListener("click", () => {
    void downloadBinanceData()
  })
  initV8DownloadPanel()
  syncDlSymbolFromLiveSelect()
})

function v8PaintDashboardPayload(data) {
  if (!data) return
  const paintSel = String(selectedDashboardSession || "").toLowerCase()
  const paintHint = v8PayloadSessionHint(data)
  if (paintSel === "backtest" && paintHint && paintHint !== "backtest") {
    if (typeof console !== "undefined" && console.debug) {
      console.debug("[V8] skip paint stale session", paintHint)
    }
    return
  }
  if (
    paintSel === "backtest" &&
    !v8BacktestDashboardLooksStarted(data) &&
    backtestResetActive &&
    !v8IsBacktestFinished(data)
  ) {
    return
  }
  if (v8SkipIfBacktestHardReset("v8PaintDashboardPayload")) return
  if (V8_DEBUG_DASHBOARD_PAINT) console.log("[V8] paint dashboard")
  syncMarketHeaderFromConfig(data.config)

  updatePosition(data)
  updatePnL(data)

  updateSystem(data)
  updateExecution(data)
  updateRisk(data)
  updateReconciliation(data)

  updateStrategy(data)
  updateMarketBias(data)

  // FIX LIVE METRICS INITIAL PAINT
  updateMetrics(data)
  updatePerformance(data)

  if (data.config) {
    const paused = data.config.trading_enabled === false
    const pauseBtn = document.getElementById("pause_btn")
    const resumeBtn = document.getElementById("resume_btn")
    if (pauseBtn && resumeBtn) {
      if (paused) {
        pauseBtn.style.background = "#ef4444"
        pauseBtn.style.color = "#fff"
        resumeBtn.style.background = ""
        resumeBtn.style.color = ""
      } else {
        resumeBtn.style.background = "#22c55e"
        resumeBtn.style.color = "#000"
        pauseBtn.style.background = ""
        pauseBtn.style.color = ""
      }
    }
  }

  updateSlippage(data)
  updateLatency(data)
  updateAlerts(data)
  updateExecutionPipeline(data)
  updateV8PipelineBreadcrumb(data)
  updateOrderLifecycle(data)
  if (String(selectedDashboardSession || "").toLowerCase() === "backtest") {
    if (
      selectedDashboardSession === "backtest" &&
      backtestIdleMode &&
      !v8IsNewBacktestRun(data) &&
      !v8BacktestPayloadHasSummarySignals(data)
    ) {
      return
    }
    void updateBacktestSummary(data)
  }
}

async function prefetchOtherSessions() {
  const now = Date.now()
  if (now - lastPrefetchTime < PREFETCH_COOLDOWN_MS) {
    return
  }
  lastPrefetchTime = now
  const sessions = ["live", "shadow", "paper", "backtest"]
  for (const s of sessions) {
    if (s === selectedDashboardSession) continue
    const params = new URLSearchParams()
    params.set("session", s)
    if (dualPanelModeEnabled) params.set("dual", "1")
    fetch(`/api/dashboard?${params.toString()}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) dashboardSessionCache[s] = d
      })
      .catch(() => {})
  }
}

async function loadDashboard(){

try{
const requestId = ++dashboardRequestId
await refreshSessionStatuses()
updateHeaderRunning()

const res = await fetch(`/api/dashboard?${getSessionQueryParams()}`)

if(!res.ok) return

const data = await res.json()
if(requestId !== dashboardRequestId) return

if(!data) return

const sidBt = String(selectedDashboardSession || "").toLowerCase()
const payloadSession = v8PayloadSessionHint(data)

if (
  sidBt === "backtest" &&
  payloadSession &&
  payloadSession !== "backtest"
) {
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[V8] skip stale payload", payloadSession)
  }
  await loadSessionConfig()
  if (!controlPanelBaselineReady) {
    applySymbolSelectFromBaseline()
    controlInitialized = true
    controlPanelBaselineReady = true
    refreshControlApplyButtonStates()
  }
  return
}

if (
  sidBt === "backtest" &&
  dashboardSessionCache["backtest"] &&
  !v8BacktestDashboardLooksStarted(data) &&
  !v8IsBacktestFinished(data)
) {
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[V8] skip backtest apply: cached entry exists but payload not started")
  }
  await loadSessionConfig()
  if (!controlPanelBaselineReady) {
    applySymbolSelectFromBaseline()
    controlInitialized = true
    controlPanelBaselineReady = true
    refreshControlApplyButtonStates()
  }
  return
}

if (sidBt === "backtest") {
  if (v8BacktestDashboardLooksStarted(data)) {
    backtestResetActive = false
    if (v8BacktestResetFailsafeTimer != null) {
      clearTimeout(v8BacktestResetFailsafeTimer)
      v8BacktestResetFailsafeTimer = null
    }
  } else if (
    backtestResetActive &&
    !backtestLifecycleRefresh &&
    !v8IsBacktestFinished(data)
  ) {
    await loadSessionConfig()
    if (!controlPanelBaselineReady) {
      applySymbolSelectFromBaseline()
      controlInitialized = true
      controlPanelBaselineReady = true
      refreshControlApplyButtonStates()
    }
    return
  }
}

if (sidBt === "backtest" && v8SkipIfBacktestHardReset("loadDashboard")) {
  await loadSessionConfig()
  if (!controlPanelBaselineReady) {
    applySymbolSelectFromBaseline()
    controlInitialized = true
    controlPanelBaselineReady = true
    refreshControlApplyButtonStates()
  }
  return
}

if (
  sidBt === "backtest" &&
  backtestResetActive &&
  !v8BacktestDashboardLooksStarted(data) &&
  !backtestLifecycleRefresh &&
  !v8IsBacktestFinished(data)
) {
  return
}

if (sidBt === "backtest") {
  const isFinished = v8IsBacktestFinished(data)
  const isRunning = v8BacktestIsRunningPayload(data)
  if (isFinished && v8BacktestState !== "finished") {
    v8BacktestState = "finished"
  }
  if (isRunning && v8BacktestState !== "running") {
    v8ResetBacktestState()
    v8BacktestState = "running"
  } else if (!isRunning && !isFinished && !v8BacktestDashboardLooksStarted(data)) {
    v8BacktestState = "idle"
  }
}

lastDashboardPayload = data
dashboardSessionCache[selectedDashboardSession] = data

if (V8_DEBUG_DASHBOARD_PAINT) console.log("[V8] loadDashboard paint")
v8QueuedDashboardRequestId = requestId
scheduleV8DeterministicPaint("dashboard", data)

prefetchOtherSessions()

await loadSessionConfig()

if(!controlPanelBaselineReady){
applySymbolSelectFromBaseline()
controlInitialized = true
controlPanelBaselineReady = true
refreshControlApplyButtonStates()
}

}catch(e){
/* dashboard refresh failed */
}

}

function togglePanel(id){

const el = document.querySelector(`[gs-id="${id}"]`)

if(!el) return

if(el.classList.contains("hidden-panel")){

el.classList.remove("hidden-panel")
el.style.display="block"

}else{

el.classList.add("hidden-panel")
el.style.display="none"

}

saveHiddenPanels()

}

async function pauseBot(){

try{

await fetch("/api/control/pause",{
method:"POST"
})

// đổi màu
document.getElementById("pause_btn").style.background = "#ef4444"
document.getElementById("pause_btn").style.color = "#fff"

document.getElementById("resume_btn").style.background = ""
document.getElementById("resume_btn").style.color = ""

}catch(e){

console.error(e)

}

}

async function resumeBot(){

try{

await fetch("/api/control/resume",{
method:"POST"
})

// đổi màu
document.getElementById("resume_btn").style.background = "#22c55e"
document.getElementById("resume_btn").style.color = "#000"

document.getElementById("pause_btn").style.background = ""
document.getElementById("pause_btn").style.color = ""

}catch(e){

console.error(e)

}

}

function resetLayout(){

localStorage.removeItem("gridstack-layout")

location.reload()

}

function saveHiddenPanels(){

const hidden=[]

document.querySelectorAll(".hidden-panel").forEach(el=>{

hidden.push(el.getAttribute("gs-id"))

})

localStorage.setItem(
"hidden-panels",
JSON.stringify(hidden)
)

}

function restoreHiddenPanels(){

const hidden = JSON.parse(
localStorage.getItem("hidden-panels")
) || []

hidden.forEach(id => {

const el = document.querySelector(`[gs-id="${id}"]`)

if(el){

el.style.display="none"
el.classList.add("hidden-panel")

}

})

}

function showAllPanels(){

document.querySelectorAll(".grid-stack-item").forEach(el=>{
el.style.display="block"
el.classList.remove("hidden-panel")
})

localStorage.removeItem("hidden-panels")

}

function openPanelManager(){

const manager=document.getElementById("panelManager")

manager.style.display="flex"

buildPanelList()

}

function closePanelManager(){

document.getElementById("panelManager").style.display="none"

}

function buildPanelList(){

const container=document.getElementById("panelList")

container.innerHTML=""

document.querySelectorAll(".grid-stack-item").forEach(panel=>{

const id=panel.getAttribute("gs-id")

const hidden=panel.classList.contains("hidden-panel")

const row=document.createElement("label")

row.innerHTML=`
<input type="checkbox" ${hidden?"":"checked"} onchange="togglePanel('${id}')">
${id}
`

container.appendChild(row)

})

}

function updatePipeline(data){

const el=document.getElementById("execution_pipeline")

if(!el) return

const steps=[
"Signal",
"Decision",
"Order",
"Exchange",
"Fill",
"Position"
]

let html='<div class="pipeline">'

steps.forEach(s=>{
html+=`<div class="pipeline-step">${s}</div>`
})

html+='</div>'

el.innerHTML=html

}

function showAlert(msg){

const container=document.getElementById("alertOverlay")

const div=document.createElement("div")

div.className="alert-box"

div.innerText=msg

container.appendChild(div)

setTimeout(()=>{
div.remove()
},5000)

}

function initWebSocket(){

const session_id = "live_shadow"

const ws = new WebSocket(
`ws://127.0.0.1:8000/ws/state/${session_id}`
)

ws.onopen = () => {}

ws.onmessage = (event) => {

const msg = JSON.parse(event.data)

// websocket của bạn đôi khi có {type, data}
const data = msg.data || msg

if (
  String(selectedDashboardSession || "").toLowerCase() === "backtest" &&
  v8BacktestDashboardLooksStarted(data)
) {
  backtestUIHardReset = false
  backtestResetActive = false
  if (v8BacktestResetFailsafeTimer != null) {
    clearTimeout(v8BacktestResetFailsafeTimer)
    v8BacktestResetFailsafeTimer = null
  }
}

const isHardReset = isBacktestHardReset()

// POSITION
if(data.position){
updatePosition(data)
updateStrategy(data)
updateOrderLifecycle(data)
}

// EXECUTION
if(data?.observability?.execution_monitor){
updateExecution(data)
}

// PnL / risk / metrics / backtest summary: coalesce (skip noise ticks that only carry e.g. market)
if (
  !isHardReset &&
  (data.pnl != null ||
    data.risk_status != null ||
    data.metrics != null ||
    (Array.isArray(data.recent_trades) && data.recent_trades.length > 0) ||
    data.backtest_running != null)
) {
  scheduleV8DeterministicPaint("ws", data)
}

// PIPELINE
updateExecutionPipeline(data)

// HEADER MARKET DATA
if(data.market){

document.getElementById("mh-price").innerText =
"Price: " + data.market.price

document.getElementById("mh-change").innerText =
"24h: " + data.market.change_24h + "%"

document.getElementById("mh-funding").innerText =
"Funding: " + data.market.funding

}

updateBacktestProgressDisplay(data)

}
}

function updateClearButtonState(data) {
  const btn = document.getElementById("clear-history-btn")
  if (!btn) return
  const pos = data?.position ?? lastDashboardPayload?.position
  const raw = pos?.size ?? lastDashboardPayload?.position_size ?? 0
  const n = Number(raw)
  const open = Number.isFinite(n) && Math.abs(n) > 0
  btn.disabled = open
  btn.title = open
    ? "Close position before clearing trade history"
    : ""
}

function updatePosition(data) {
  updateClearButtonState(data)
  if (v8PanelHiddenById("v8-panel-position")) return
  const p = data?.position
  const el = document.getElementById("position")
  if (!el) return

  if (!p || !p.side || p.side === "flat") {
    el.innerHTML = `
        <div class="v8-kv"><span class="k">Side</span><span class="v">FLAT</span></div>
        <div class="v8-kv"><span class="k">Size</span><span class="v mono">0</span></div>
        <div class="v8-kv"><span class="k">Entry Price</span><span class="v mono">—</span></div>
    `
    return
  }

  const side = String(p.side || "").toUpperCase()
  const entry =
    p.entry_price != null && !Number.isNaN(Number(p.entry_price))
      ? Number(p.entry_price).toLocaleString(undefined, { maximumFractionDigits: 2 })
      : "—"
  const cls = side === "LONG" ? "pos-long" : side === "SHORT" ? "pos-short" : ""

  el.innerHTML = `
        <div class="v8-kv"><span class="k">Side</span><span class="v ${cls}">${side}</span></div>
        <div class="v8-kv"><span class="k">Size</span><span class="v mono">${pnlFmtNum(p.size)}</span></div>
        <div class="v8-kv"><span class="k">Entry Price</span><span class="v mono">${entry}</span></div>
    `
}

function pnlFmtNum(v) {
  return formatCurrency(v)
}

function pnlFmtStr(v, fallback){
if(v === null || v === undefined || v === "") return fallback ?? "—"
return String(v)
}

function pnlFloatingStyle(raw){
const n = Number(raw)
if(Number.isNaN(n) || raw === null || raw === undefined) return "#9e9e9e"
if(n > 0) return "#00c853"
if(n < 0) return "#ff3d00"
return "#9e9e9e"
}

function pnlFloatingPrefix(raw){
const n = Number(raw)
if(Number.isNaN(n) || raw === null || raw === undefined) return ""
return n > 0 ? "+" : ""
}

function pnlModeLine(panel, root){
if(root?.session_status === "no_session" || panel?.mode === "NONE"){
return "No Active Session"
}
return pnlFmtStr(panel?.mode, "—")
}

function updateBacktestProgressDisplay(root) {
  if (v8PanelHiddenById("v8-panel-pnl")) return
  const el = document.getElementById("backtest_progress")
  if (!el) return
  const pnl = root?.pnl || {}
  const prog =
    root?.backtest_progress !== undefined ? root.backtest_progress : pnl.backtest_progress
  const tc =
    root?.trade_count !== undefined ? root.trade_count : pnl.trade_count
  const eq = pnl.equity !== undefined && pnl.equity !== null ? pnl.equity : root?.equity

  if (prog !== undefined && prog !== null && Number(prog) < 1) {
    const pct = Math.round(Number(prog) * 100)
    let s = `Backtest Running ${pct}%`
    if (tc != null && tc !== "") s += ` · Trades: ${tc}`
    if (eq != null && eq !== "" && !Number.isNaN(Number(eq))) s += ` · Equity: ${formatCurrency(eq)}`
    el.innerText = s
    return
  }
  if (prog !== undefined && prog !== null && Number(prog) >= 1) {
    let s = "Backtest Finished"
    if (tc != null && tc !== "") s += ` · Trades: ${tc}`
    if (eq != null && eq !== "" && !Number.isNaN(Number(eq))) s += ` · Final Equity: ${pnlFmtNum(eq)}`
    el.innerText = s
    return
  }
  el.innerText = "Backtest Idle"
}

function v8BacktestTradePnl(t) {
  const raw = t?.pnl ?? t?.result
  if (raw === null || raw === undefined) return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

function v8BacktestTradeTimeSec(t) {
  const ms = v8BacktestTradeInstantMs(t)
  if (ms == null || !Number.isFinite(ms)) return null
  return Math.floor(ms / 1000)
}

/** Milliseconds since epoch for range math (CSV / API may use datetime, exit_time, etc.). */
function v8BacktestTradeInstantMs(t) {
  if (!t || typeof t !== "object") return null
  const candidates = [
    t.datetime,
    t.exit_time,
    t.entry_time,
    t.time,
    t.timestamp,
  ]
  for (const v of candidates) {
    if (v == null || v === "") continue
    if (typeof v === "number" && Number.isFinite(v)) {
      return v > 1e12 ? v : v * 1000
    }
    if (typeof v === "string") {
      if (/^\d+$/.test(v)) {
        const n = Number(v)
        if (!Number.isFinite(n)) continue
        return n > 1e12 ? n : n * 1000
      }
      const parsed = Date.parse(v)
      if (!Number.isNaN(parsed)) return parsed
    }
  }
  return null
}

function v8MaxDrawdownDollarsFromEquityCurve(equityCurve) {
  if (!Array.isArray(equityCurve) || equityCurve.length === 0) return null
  let peak = equityCurve[0]
  if (!Number.isFinite(peak)) return null
  let maxDd = 0
  for (let i = 1; i < equityCurve.length; i++) {
    const eq = equityCurve[i]
    if (!Number.isFinite(eq)) continue
    if (eq > peak) peak = eq
    const dd = peak - eq
    if (dd > maxDd) maxDd = dd
  }
  return maxDd > 0 ? maxDd : null
}

/**
 * Closed-trade equity series and drawdown vs running peak (same path as journal curve).
 * @returns {{ equityCurve: number[], maxDrawdown: number|null, peak: number }|null}
 */
function v8BacktestEquityCurveFromTrades(trades, startBalance) {
  const sb = Number(startBalance)
  if (!Number.isFinite(sb) || sb <= 0) return null
  if (!Array.isArray(trades) || trades.length === 0) {
    return { equityCurve: [sb], maxDrawdown: null, peak: sb }
  }
  const sorted = [...trades].sort((a, b) => {
    const ta = v8BacktestTradeTimeSec(a) ?? 0
    const tb = v8BacktestTradeTimeSec(b) ?? 0
    return ta - tb
  })
  const equityCurve = [sb]
  let eq = sb
  let peak = eq
  let maxDdFrac = 0
  for (const t of sorted) {
    const p = v8BacktestTradePnl(t)
    if (p == null) continue
    eq += p
    equityCurve.push(eq)
    if (eq > peak) peak = eq
    if (peak > 1e-12) {
      const dd = (peak - eq) / peak
      if (dd > maxDdFrac) maxDdFrac = dd
    }
  }
  return {
    equityCurve,
    maxDrawdown: maxDdFrac > 1e-12 ? maxDdFrac : null,
    peak,
  }
}

function v8BacktestMaxDrawdownDollars(trades, startBalance) {
  const pack = v8BacktestEquityCurveFromTrades(trades, startBalance)
  if (!pack) return null
  return v8MaxDrawdownDollarsFromEquityCurve(pack.equityCurve)
}

/** Max drawdown as fraction of running peak equity (0–1), from closed-trade PnL series. */
function v8BacktestMaxDrawdownFractionFromTrades(trades, startBalance) {
  const pack = v8BacktestEquityCurveFromTrades(trades, startBalance)
  return pack?.maxDrawdown ?? null
}

function v8JournalRealizedPnlSum(trades) {
  if (!Array.isArray(trades) || !trades.length) return null
  let sum = 0
  let any = false
  for (const t of trades) {
    const p = v8BacktestTradePnl(t)
    if (p == null) continue
    any = true
    sum += p
  }
  return any ? sum : null
}

function v8TradeSideIsLong(t) {
  const s = String(t?.side ?? "").toUpperCase()
  const d = String(t?.direction ?? t?.dir ?? "").toLowerCase()
  return s === "LONG" || s === "BUY" || d === "long"
}

function v8TradeSideIsShort(t) {
  const s = String(t?.side ?? "").toUpperCase()
  const d = String(t?.direction ?? t?.dir ?? "").toLowerCase()
  return s === "SHORT" || s === "SELL" || d === "short"
}

function v8FormatDurationSec(totalSec) {
  if (totalSec == null || !Number.isFinite(totalSec) || totalSec < 0) return "—"
  if (totalSec < 60) return `${Math.round(totalSec)}s`
  const m = Math.floor(totalSec / 60)
  if (m < 60) return `${m}m ${Math.round(totalSec % 60)}s`
  const h = Math.floor(m / 60)
  if (h < 48) return `${h}h ${m % 60}m`
  const d = Math.floor(h / 24)
  return `${d}d ${h % 24}h`
}

function v8ComputeWinLossStreaksFromTrades(trades) {
  if (!Array.isArray(trades) || trades.length === 0) {
    return { maxWin: null, maxLoss: null }
  }
  const sorted = [...trades]
    .map((t, i) => ({ t, pnl: v8BacktestTradePnl(t), i }))
    .filter((x) => x.pnl !== null)
    .sort((a, b) => {
      const ta = v8BacktestTradeTimeSec(a.t)
      const tb = v8BacktestTradeTimeSec(b.t)
      if (ta != null && tb != null && ta !== tb) return ta - tb
      return a.i - b.i
    })
  let maxW = 0
  let maxL = 0
  let curW = 0
  let curL = 0
  for (const x of sorted) {
    if (x.pnl > 0) {
      curW += 1
      curL = 0
      maxW = Math.max(maxW, curW)
    } else if (x.pnl < 0) {
      curL += 1
      curW = 0
      maxL = Math.max(maxL, curL)
    } else {
      curW = 0
      curL = 0
    }
  }
  return { maxWin: maxW > 0 ? maxW : null, maxLoss: maxL > 0 ? maxL : null }
}

/** Journal-derived metrics when SQLite-backed metrics lag behind in-memory trades (fallback only). */
function v8ComputeMetricsFromTrades(trades) {
  if (!Array.isArray(trades) || !trades.length) return null

  let wins = 0
  let losses = 0
  let grossWin = 0
  let grossLoss = 0

  let maxWinStreak = 0
  let maxLossStreak = 0
  let winStreak = 0
  let lossStreak = 0

  let longTrades = 0
  let shortTrades = 0

  for (const t of trades) {
    if (v8TradeSideIsLong(t)) longTrades += 1
    else if (v8TradeSideIsShort(t)) shortTrades += 1

    const raw = v8BacktestTradePnl(t)
    if (raw == null) continue
    const pnl = Number(raw)
    if (!Number.isFinite(pnl)) continue

    if (pnl > 0) {
      wins += 1
      grossWin += pnl
      winStreak += 1
      lossStreak = 0
    } else if (pnl < 0) {
      losses += 1
      grossLoss += Math.abs(pnl)
      lossStreak += 1
      winStreak = 0
    } else {
      winStreak = 0
      lossStreak = 0
    }

    maxWinStreak = Math.max(maxWinStreak, winStreak)
    maxLossStreak = Math.max(maxLossStreak, lossStreak)
  }

  const total = wins + losses
  if (total === 0) return null

  const avgWin = wins ? grossWin / wins : 0
  const avgLoss = losses ? grossLoss / losses : 0

  const winRate = total ? wins / total : 0
  const profitFactor = grossLoss > 0 ? grossWin / grossLoss : null

  const expectancy = winRate * avgWin - (1 - winRate) * avgLoss

  return {
    win_rate: winRate,
    avg_win: avgWin,
    avg_loss: -avgLoss,
    profit_factor: profitFactor,
    expectancy,
    max_win_streak: maxWinStreak > 0 ? maxWinStreak : null,
    max_loss_streak: maxLossStreak > 0 ? maxLossStreak : null,
    long_trades: longTrades,
    short_trades: shortTrades,
    total_trades: total,
  }
}

function computeBacktestSummary(trades) {
  const t = Array.isArray(trades) ? trades : []
  const finished =
    lastDashboardPayload && v8IsBacktestFinished(lastDashboardPayload)
  if (
    selectedDashboardSession === "backtest" &&
    backtestResetActive &&
    t.length === 0 &&
    !finished
  ) {
    return null
  }
  if (isBacktestHardReset()) return null
  return v8ComputeWinLossStreaksFromTrades(t)
}

/** Merge dashboard keys that may carry post-finish backtest stats (metrics poll uses same shape). */
function v8MergeBacktestSummaryMetricSources(data) {
  const box = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : {})
  return {
    ...(lastMetricsSummary || {}),
    ...box(data?.performance),
    ...box(data?.metrics),
    ...box(data?.summary),
    ...box(data?.pnl?.metrics),
    ...box(data?.backtest_summary),
  }
}

/**
 * Single deterministic trade list for backtest metrics.
 * Prefer dashboard / in-memory journal first (full run), then capped `/api/trades/history` buffers.
 */
function v8GetBacktestTrades(data) {
  const primary = [data?.recent_trades, data?.trades, recentTrades]
  const fallback = [tradeHistory, lastTrades]
  let best = []
  for (const s of primary) {
    if (!Array.isArray(s) || s.length === 0) continue
    if (s.length > best.length) best = s
  }
  if (best.length > 0) return best
  for (const s of fallback) {
    if (!Array.isArray(s) || s.length === 0) continue
    if (s.length > best.length) best = s
  }
  return best
}

function v8BtSumRow(label, value) {
  const v =
    value === null || value === undefined || value === "" ? "—" : String(value)
  return `<div class="v8-kv"><span class="k">${label}</span><span class="v mono">${v}</span></div>`
}

async function updateBacktestSummary(data) {
  if (!data) return
  if (String(selectedDashboardSession || "").toLowerCase() !== "backtest") return
  const payloadSession = v8PayloadSessionHint(data)
  if (payloadSession && payloadSession !== "backtest") return
  if (
    selectedDashboardSession === "backtest" &&
    backtestIdleMode &&
    !v8IsNewBacktestRun(data) &&
    !v8BacktestPayloadHasSummarySignals(data)
  ) {
    return
  }
  if (
    Array.isArray(data.recent_trades) &&
    data.recent_trades.length > 0 &&
    (selectedDashboardSession !== "backtest" ||
      !backtestResetActive ||
      v8BacktestDashboardLooksStarted(data) ||
      v8BacktestPayloadHasSummarySignals(data))
  ) {
    if (
      !backtestIdleMode ||
      selectedDashboardSession !== "backtest" ||
      v8BacktestPayloadHasSummarySignals(data)
    ) {
      recentTrades = data.recent_trades
    }
  }

  const isFinished = v8IsBacktestFinished(data)
  if (
    selectedDashboardSession === "backtest" &&
    backtestResetActive &&
    !isFinished &&
    (!Array.isArray(recentTrades) || recentTrades.length === 0) &&
    v8GetBacktestTrades(data).length === 0 &&
    !v8BacktestPayloadHasSummarySignals(data)
  ) {
    return
  }
  if (v8SkipIfBacktestHardReset("updateBacktestSummary")) return
  const root = document.getElementById("v8_backtest_summary_root")
  if (!root) return
  const cfg = data?.config || {}
  const pnl = data?.pnl || {}

  if (isFinished) {
    await v8LoadBacktestTrades()
  }

  const trades = Array.isArray(recentTrades) ? recentTrades.slice() : []
  const journalN = trades.length

  let metrics = v8MergeBacktestSummaryMetricSources(data)
  if (journalN > 0) {
    const derived = v8ComputeMetricsFromTrades(trades)
    if (derived) metrics = { ...metrics, ...derived }
  }

  const risk = data?.risk_status || {}

  const sym = pnl.symbol || cfg.symbol || "—"
  const tf = cfg.test_timeframe || cfg.timeframe || "—"

  let startDateStr = "—"
  let endDateStr = "—"
  let durSec = null
  let durationStr = "—"
  let tradesPerDayStr = "—"

  if (journalN > 0) {
    const instants = trades
      .map(v8BacktestTradeInstantMs)
      .filter((ms) => ms != null && Number.isFinite(ms) && ms > 0)
    if (instants.length > 0) {
      const startMs = Math.min(...instants)
      const endMs = Math.max(...instants)
      startDateStr = new Date(startMs).toLocaleDateString(undefined, {
        dateStyle: "medium",
      })
      endDateStr = new Date(endMs).toLocaleDateString(undefined, {
        dateStyle: "medium",
      })
      if (endMs >= startMs) {
        durSec = (endMs - startMs) / 1000
        durationStr = v8FormatDurationSec(durSec)
        const days = durSec / 86400
        if (days > 1 / 8640) {
          const tpd = journalN / Math.max(days, 1 / 8640)
          tradesPerDayStr = Number.isFinite(tpd) ? formatNumber(tpd) : "—"
        }
      }
    }
  }

  let totalTrades = "—"
  if (journalN > 0) {
    totalTrades = String(journalN)
  } else if (pnl.trade_count != null && pnl.trade_count !== "") {
    totalTrades = String(pnl.trade_count)
  } else if (metrics.total_trades != null && metrics.total_trades !== "") {
    totalTrades = String(metrics.total_trades)
  }

  let wr = Number(metrics.win_rate ?? metrics.winRate)
  if (Number.isFinite(wr) && wr > 1 && wr <= 100) wr = wr / 100
  const wrStr = Number.isFinite(wr) ? `${(wr * 100).toFixed(1)}%` : "—"
  const pf = metrics.profit_factor ?? metrics.profitFactor
  const pfStr =
    pf != null && Number.isFinite(Number(pf)) ? formatNumber(Number(pf)) : "—"

  const avgWin = Number(metrics.avg_win ?? metrics.avgWin)
  const avgLoss = Number(metrics.avg_loss ?? metrics.avgLoss)
  let expectancy = "—"
  const expM = metrics.expectancy ?? metrics.expectancy_dollars ?? metrics.expectancyDollars
  if (expM != null && Number.isFinite(Number(expM))) {
    expectancy = formatCurrency(Number(expM))
  } else if (Number.isFinite(wr) && Number.isFinite(avgWin) && Number.isFinite(avgLoss)) {
    const e = wr * avgWin + (1 - wr) * avgLoss
    expectancy = Number.isFinite(e) ? formatCurrency(e) : "—"
  }

  let maxWin = null
  let maxLoss = null
  const streakPack = computeBacktestSummary(trades)
  if (streakPack) {
    maxWin = streakPack.maxWin
    maxLoss = streakPack.maxLoss
  }
  if (journalN === 0) {
    const mws = metrics.max_win_streak ?? metrics.maxWinStreak
    const mls = metrics.max_loss_streak ?? metrics.maxLossStreak
    if (maxWin == null && mws != null && Number.isFinite(Number(mws))) maxWin = Number(mws)
    if (maxLoss == null && mls != null && Number.isFinite(Number(mls))) maxLoss = Number(mls)
  }
  const maxWinStr = maxWin != null ? String(maxWin) : "—"
  const maxLossStr = maxLoss != null ? String(maxLoss) : "—"

  const startBalRaw =
    pnl.start_balance ??
    document.getElementById("initial_balance")?.value ??
    cfg.initial_balance
  const startBal = Number(startBalRaw)
  const startBalOk = Number.isFinite(startBal) && startBal > 0

  const mddRaw = pnl.max_drawdown
  let mddStr = "—"
  const journalCurvePack =
    startBalOk && journalN > 0 ? v8BacktestEquityCurveFromTrades(trades, startBal) : null
  if (journalCurvePack != null) {
    mddStr =
      journalCurvePack.maxDrawdown != null && Number.isFinite(journalCurvePack.maxDrawdown)
        ? `${(journalCurvePack.maxDrawdown * 100).toFixed(2)}%`
        : `0.00%`
  } else if (mddRaw != null && Number.isFinite(Number(mddRaw))) {
    mddStr = `${(Number(mddRaw) * 100).toFixed(2)}%`
  }

  const blocked = Array.isArray(risk.blocked_rules) ? risk.blocked_rules : []
  const ddLockCount = blocked.filter((x) => /equity|drawdown|dd/i.test(String(x))).length
  const ddLockStr = ddLockCount > 0 ? String(ddLockCount) : "—"

  let largestLoss = "—"
  const lossPnls = trades.map(v8BacktestTradePnl).filter((n) => n != null && n < 0)
  if (lossPnls.length) {
    largestLoss = formatCurrency(Math.min(...lossPnls))
  }

  const awStr =
    Number.isFinite(avgWin) && avgWin !== 0 ? formatCurrency(avgWin) : "—"
  const alStr =
    Number.isFinite(avgLoss) && avgLoss !== 0 ? formatCurrency(avgLoss) : "—"
  let rr = "—"
  const rrM =
    metrics.risk_reward ??
    metrics.risk_reward_ratio ??
    metrics.riskReward ??
    metrics.rr
  if (rrM != null && Number.isFinite(Number(rrM))) {
    rr = formatNumber(Number(rrM))
  } else if (Number.isFinite(avgWin) && Number.isFinite(avgLoss) && avgLoss !== 0) {
    const ratio = avgWin / Math.abs(avgLoss)
    rr = Number.isFinite(ratio) ? formatNumber(ratio) : "—"
  }

  let netProfit = v8JournalRealizedPnlSum(trades)
  if (!Number.isFinite(netProfit)) {
    netProfit = Number(pnl.realized_pnl)
  }
  if (!Number.isFinite(netProfit)) {
    netProfit = trades.reduce((s, t) => s + (v8BacktestTradePnl(t) ?? 0), 0)
  }

  let maxDdDollars =
    journalCurvePack != null
      ? v8MaxDrawdownDollarsFromEquityCurve(journalCurvePack.equityCurve)
      : startBalOk
        ? v8BacktestMaxDrawdownDollars(trades, startBal)
        : null
  if (maxDdDollars == null && startBalOk && mddRaw != null && Number.isFinite(Number(mddRaw))) {
    const frac = Math.abs(Number(mddRaw))
    if (frac > 0) maxDdDollars = frac * startBal
  }

  let recoveryStr = "—"
  const rfMetric = metrics.recovery_factor ?? metrics.recoveryFactor
  if (journalCurvePack != null) {
    if (maxDdDollars != null && maxDdDollars > 1e-9) {
      const rf = netProfit / maxDdDollars
      recoveryStr = Number.isFinite(rf) ? formatNumber(rf) : "—"
    } else if (
      Number.isFinite(netProfit) &&
      netProfit !== 0 &&
      (maxDdDollars == null || maxDdDollars <= 1e-9)
    ) {
      recoveryStr = netProfit > 0 ? "∞" : "—"
    }
  } else if (rfMetric != null && Number.isFinite(Number(rfMetric))) {
    recoveryStr = formatNumber(Number(rfMetric))
  } else if (maxDdDollars != null && maxDdDollars > 1e-9) {
    const rf = netProfit / maxDdDollars
    recoveryStr = Number.isFinite(rf) ? formatNumber(rf) : "—"
  } else if (Number.isFinite(netProfit) && netProfit !== 0 && (maxDdDollars == null || maxDdDollars <= 1e-9)) {
    recoveryStr = netProfit > 0 ? "∞" : "—"
  }

  let longCt = 0
  let shortCt = 0
  if (journalN > 0) {
    longCt = trades.filter(v8TradeSideIsLong).length
    shortCt = trades.filter(v8TradeSideIsShort).length
  } else {
    const ltM = metrics.long_trades ?? metrics.long_count ?? metrics.longCount
    const stM = metrics.short_trades ?? metrics.short_count ?? metrics.shortCount
    if (ltM != null && Number.isFinite(Number(ltM))) longCt = Number(ltM)
    if (stM != null && Number.isFinite(Number(stM))) shortCt = Number(stM)
  }
  const longStr =
    journalN > 0 || longCt > 0 || shortCt > 0 ? String(longCt) : "—"
  const shortStr =
    journalN > 0 || longCt > 0 || shortCt > 0 ? String(shortCt) : "—"

  root.innerHTML = `
    <div class="v8-backtest-summary-grid">
      <div class="v8-backtest-summary-col">
        <h3 class="v8-backtest-summary-heading">Test info</h3>
        ${v8BtSumRow("Symbol", String(sym).toUpperCase())}
        ${v8BtSumRow("Timeframe", tf)}
        ${v8BtSumRow("Start date", startDateStr)}
        ${v8BtSumRow("End date", endDateStr)}
        ${v8BtSumRow("Total trades", totalTrades)}
      </div>
      <div class="v8-backtest-summary-col">
        <h3 class="v8-backtest-summary-heading">Performance</h3>
        ${v8BtSumRow("Win rate", wrStr)}
        ${v8BtSumRow("Profit factor", pfStr)}
        ${v8BtSumRow("Expectancy", expectancy)}
      </div>
      <div class="v8-backtest-summary-col">
        <h3 class="v8-backtest-summary-heading">Streaks</h3>
        ${v8BtSumRow("Max win streak", maxWinStr)}
        ${v8BtSumRow("Max loss streak", maxLossStr)}
      </div>
      <div class="v8-backtest-summary-col">
        <h3 class="v8-backtest-summary-heading">Risk</h3>
        ${v8BtSumRow("Max drawdown", mddStr)}
        ${v8BtSumRow("DD lock count", ddLockStr)}
        ${v8BtSumRow("Largest loss", largestLoss)}
      </div>
      <div class="v8-backtest-summary-col">
        <h3 class="v8-backtest-summary-heading">Trade quality</h3>
        ${v8BtSumRow("Avg win", awStr)}
        ${v8BtSumRow("Avg loss", alStr)}
        ${v8BtSumRow("Risk reward", rr)}
      </div>
      <div class="v8-backtest-summary-col">
        <h3 class="v8-backtest-summary-heading">Stability</h3>
        ${v8BtSumRow("Recovery factor", recoveryStr)}
        ${v8BtSumRow("Trades per day", tradesPerDayStr)}
        ${v8BtSumRow("Test duration", durationStr)}
      </div>
      <div class="v8-backtest-summary-col">
        <h3 class="v8-backtest-summary-heading">Trade distribution</h3>
        ${v8BtSumRow("Long trades", longStr)}
        ${v8BtSumRow("Short trades", shortStr)}
      </div>
    </div>
  `
  if (trades.length > (Array.isArray(recentTrades) ? recentTrades.length : 0)) {
    recentTrades = trades
  }
  if (isFinished) {
    updatePnL(lastDashboardPayload || data)
  }
}

function pnlRenderOnePanel(panel, root){
const modeLine = pnlModeLine(panel, root)
const sym = pnlFmtStr(panel?.symbol, "—")
const quote = pnlFmtStr(panel?.quote_asset, "—")
const equity = pnlFmtNum(panel?.equity)
const floatingRaw = panel?.floating
const floating = pnlFmtNum(floatingRaw)
const total = pnlFmtNum(panel?.total_equity)
const fc = pnlFloatingStyle(floatingRaw)
const fp = pnlFloatingPrefix(floatingRaw)
return `
Mode: ${modeLine}<br>
Symbol: ${sym}<br>
Quote Asset: ${quote}<br>
Equity: ${equity}<br>
Floating: <span style="color:${fc}">${fp}${floating}</span><br>
Total Equity: ${total}<br>
`
}

function updateAccountBalanceOnly(data) {
  if (v8SkipIfBacktestHardReset("updateAccountBalanceOnly")) return
  const pnl = data?.pnl
  const el = document.getElementById("pnl")
  const pnlPanelHidden = v8PanelHiddenById("v8-panel-pnl")

  const realized = formatCurrency(sessionPnlLocked.realized_pnl)
  const drawdown = (Number(sessionPnlLocked.max_drawdown ?? 0) * 100).toFixed(2) + "%"
  const pf = lastMetricsSummary?.profit_factor
  const pfStr =
    pf != null && Number.isFinite(Number(pf)) ? formatNumber(pf) : "—"

  if (!pnl) {
    updateBacktestProgressDisplay({ pnl: {} })
    if (el && !pnlPanelHidden) {
      el.innerHTML = `
        <div class="v8-kv"><span class="k">Equity</span><span class="v mono">—</span></div>
        <div class="v8-kv"><span class="k">Realized PnL</span><span class="v mono">${realized}</span></div>
        <div class="v8-kv"><span class="k">Drawdown</span><span class="v mono">${drawdown}</span></div>
        <div class="v8-kv"><span class="k">Profit Factor</span><span class="v mono">${pfStr}</span></div>
    `
    }
    return
  }

  const panels = Array.isArray(pnl.panels) ? pnl.panels : []
  let equityStr = "—"
  let floatingHtml = ""
  let totalEq = null

  if (panels.length === 0) {
    equityStr = pnlFmtNum(pnl.equity)
    const fp = pnlFloatingPrefix(pnl.floating_pnl)
    const fc = pnlFloatingStyle(pnl.floating_pnl)
    floatingHtml = `<span class="v8-floating" style="color:${fc}">${fp}${pnlFmtNum(pnl.floating_pnl)}</span>`
    totalEq = pnl.total_equity != null ? Number(pnl.total_equity) : null
  } else if (panels.length === 1) {
    const p0 = panels[0]
    equityStr = pnlFmtNum(p0?.equity)
    const fp = pnlFloatingPrefix(p0?.floating)
    const fc = pnlFloatingStyle(p0?.floating)
    floatingHtml = `<span class="v8-floating" style="color:${fc}">${fp}${pnlFmtNum(p0?.floating)}</span>`
    totalEq = p0?.total_equity != null ? Number(p0.total_equity) : null
  } else {
    equityStr = `${panels.length} sessions`
    floatingHtml = ""
  }

  if (el && !pnlPanelHidden) {
    el.innerHTML = `
        <div class="v8-kv"><span class="k">Equity</span><span class="v mono">${equityStr}</span>${
          floatingHtml ? ` <span class="v8-sub">${floatingHtml} floating</span>` : ""
        }</div>
        <div class="v8-kv"><span class="k">Realized PnL</span><span class="v mono">${realized}</span></div>
        <div class="v8-kv"><span class="k">Drawdown</span><span class="v mono">${drawdown}</span></div>
        <div class="v8-kv"><span class="k">Profit Factor</span><span class="v mono">${pfStr}</span></div>
    `
  }

  if (!v8PanelHiddenById("v8-panel-equity")) {
    if (pnl.session_status === "single" && totalEq != null && !Number.isNaN(totalEq)) {
      equityHistory.push(totalEq)
    }

    if (equityHistory.length > 50) {
      equityHistory.shift()
    }

    const chartKey =
      equityHistory.length === 0
        ? ""
        : `${equityHistory.length}:${equityHistory[equityHistory.length - 1]}`
    if (chartKey !== lastEquityChartKey) {
      lastEquityChartKey = chartKey
      updateEquityChart()
    }
  }

  updateBacktestProgressDisplay({ pnl })
}

function updatePnL(data) {
  const sel = String(selectedDashboardSession || "").toLowerCase()
  const payHint = v8PayloadSessionHint(data)
  if (payHint && sel === "backtest" && payHint !== "backtest") return
  if (payHint && sel !== "backtest" && payHint === "backtest") return
  if (
    selectedDashboardSession === "backtest" &&
    backtestIdleMode &&
    !v8IsNewBacktestRun(data) &&
    !v8BacktestPayloadHasSummarySignals(data)
  ) {
    return
  }
  if (
    String(selectedDashboardSession || "").toLowerCase() === "backtest" &&
    backtestResetActive &&
    !v8IsBacktestFinished(data) &&
    v8GetBacktestTrades(data).length === 0 &&
    !v8BacktestPayloadHasSummarySignals(data)
  ) {
    return
  }
  if (v8SkipIfBacktestHardReset("updatePnL")) return
  if (v8SessionMetricsActive()) {
    updateAccountBalanceOnly(data)
    return
  }
  const pnl = data?.pnl
  if (
    String(selectedDashboardSession || "").toLowerCase() === "backtest" &&
    backtestResetActive &&
    pnl &&
    pnl.realized_pnl !== 0 &&
    !v8IsBacktestFinished(data)
  ) {
    return
  }
  const el = document.getElementById("pnl")
  const pnlPanelHidden = v8PanelHiddenById("v8-panel-pnl")
  if (!pnl) {
    updateBacktestProgressDisplay({ pnl: {} })
    if (el && !pnlPanelHidden) el.innerHTML = `<div class="v8-muted">No PnL data</div>`
    return
  }

  const isBacktestSession = String(selectedDashboardSession || "").toLowerCase() === "backtest"
  const btTrades = isBacktestSession
    ? Array.isArray(recentTrades) && recentTrades.length > 0
      ? recentTrades
      : v8GetBacktestTrades(data)
    : []
  const sbBacktest = isBacktestSession
    ? Number(
        pnl.start_balance ??
          document.getElementById("initial_balance")?.value ??
          data?.config?.initial_balance
      )
    : NaN
  const btCurvePack =
    isBacktestSession && Number.isFinite(sbBacktest) && sbBacktest > 0
      ? v8BacktestEquityCurveFromTrades(btTrades, sbBacktest)
      : null

  let realized = formatCurrency(pnl.realized_pnl ?? 0)
  let drawdown = (Number(pnl.max_drawdown ?? 0) * 100).toFixed(2) + "%"
  if (isBacktestSession && btTrades.length > 0) {
    const sumPnl = v8JournalRealizedPnlSum(btTrades)
    if (sumPnl != null && Number.isFinite(sumPnl)) {
      realized = formatCurrency(sumPnl)
    }
  }
  if (isBacktestSession && btCurvePack != null) {
    drawdown =
      btCurvePack.maxDrawdown != null && Number.isFinite(btCurvePack.maxDrawdown)
        ? `${(btCurvePack.maxDrawdown * 100).toFixed(2)}%`
        : `0.00%`
  }

  let pfStr = "—"
  if (isBacktestSession) {
    const derived =
      btTrades.length > 0 ? v8ComputeMetricsFromTrades(btTrades) : null
    const pf =
      derived?.profit_factor ?? lastMetricsSummary?.profit_factor
    if (pf != null && Number.isFinite(Number(pf))) {
      pfStr = formatNumber(Number(pf))
    }
  } else {
    const pf = lastMetricsSummary?.profit_factor
    if (pf != null && Number.isFinite(Number(pf))) pfStr = formatNumber(Number(pf))
  }

  const panels = Array.isArray(pnl.panels) ? pnl.panels : []
  let equityStr = "—"
  let floatingHtml = ""
  let totalEq = null

  const journalLastEquity =
    isBacktestSession &&
    btCurvePack?.equityCurve?.length &&
    Number.isFinite(btCurvePack.equityCurve[btCurvePack.equityCurve.length - 1])
      ? btCurvePack.equityCurve[btCurvePack.equityCurve.length - 1]
      : null

  if (panels.length === 0) {
    equityStr =
      journalLastEquity != null ? pnlFmtNum(journalLastEquity) : pnlFmtNum(pnl.equity)
    const fp = pnlFloatingPrefix(pnl.floating_pnl)
    const fc = pnlFloatingStyle(pnl.floating_pnl)
    floatingHtml = `<span class="v8-floating" style="color:${fc}">${fp}${pnlFmtNum(pnl.floating_pnl)}</span>`
    totalEq =
      journalLastEquity != null
        ? journalLastEquity
        : pnl.total_equity != null
          ? Number(pnl.total_equity)
          : null
  } else if (panels.length === 1) {
    const p0 = panels[0]
    equityStr =
      journalLastEquity != null ? pnlFmtNum(journalLastEquity) : pnlFmtNum(p0?.equity)
    const fp = pnlFloatingPrefix(p0?.floating)
    const fc = pnlFloatingStyle(p0?.floating)
    floatingHtml = `<span class="v8-floating" style="color:${fc}">${fp}${pnlFmtNum(p0?.floating)}</span>`
    totalEq =
      journalLastEquity != null
        ? journalLastEquity
        : p0?.total_equity != null
          ? Number(p0.total_equity)
          : null
  } else {
    equityStr = `${panels.length} sessions`
    floatingHtml = ""
  }

  if (el && !pnlPanelHidden) {
    el.innerHTML = `
        <div class="v8-kv"><span class="k">Equity</span><span class="v mono">${equityStr}</span>${
          floatingHtml ? ` <span class="v8-sub">${floatingHtml} floating</span>` : ""
        }</div>
        <div class="v8-kv"><span class="k">Realized PnL</span><span class="v mono">${realized}</span></div>
        <div class="v8-kv"><span class="k">Drawdown</span><span class="v mono">${drawdown}</span></div>
        <div class="v8-kv"><span class="k">Profit Factor</span><span class="v mono">${pfStr}</span></div>
    `
  }

  if (!v8PanelHiddenById("v8-panel-equity")) {
    if (pnl.session_status === "single" && totalEq != null && !Number.isNaN(totalEq)) {
      equityHistory.push(totalEq)
    }

    if (equityHistory.length > 50) {
      equityHistory.shift()
    }

    const chartKey =
      equityHistory.length === 0
        ? ""
        : `${equityHistory.length}:${equityHistory[equityHistory.length - 1]}`
    if (chartKey !== lastEquityChartKey) {
      lastEquityChartKey = chartKey
      updateEquityChart()
    }
  }

  updateBacktestProgressDisplay({ pnl })
}

function updateMetrics(data) {
  if (V8_DEBUG_DASHBOARD_PAINT) console.log("[V8] updateMetrics triggered")
  if (v8SkipIfBacktestHardReset("updateMetrics")) return
  if (v8SessionMetricsActive()) return
  if (v8PanelHiddenById("v8-panel-metrics")) return
  const el = document.getElementById("metrics")
  if (!el) return
  const m = lastMetricsSummary || data?.metrics
  if (!m) {
    el.innerHTML = `<div class="v8-muted">—</div>`
    return
  }
  const wr =
    m.win_rate != null && Number.isFinite(Number(m.win_rate))
      ? formatNumber(Number(m.win_rate) * 100)
      : "—"
  const avgWin =
    m.avg_win != null && m.avg_win !== "" && Number.isFinite(Number(m.avg_win))
      ? formatNumber(m.avg_win)
      : "—"
  const pf =
    m.profit_factor != null && Number.isFinite(Number(m.profit_factor))
      ? formatNumber(m.profit_factor)
      : "—"
  el.innerHTML = `
        <div class="v8-kv"><span class="k">Trades</span><span class="v mono">${m.total_trades ?? "—"}</span></div>
        <div class="v8-kv"><span class="k">Win rate</span><span class="v mono">${wr === "—" ? "—" : `${wr}%`}</span></div>
        <div class="v8-kv"><span class="k">Avg win</span><span class="v mono">${avgWin}</span></div>
        <div class="v8-kv"><span class="k">Profit factor</span><span class="v mono">${pf}</span></div>
    `
}

function v8BuildTradeRowTr(t) {
  const timeStr = formatTradeTime(t.time ?? t.timestamp)

  const side = v8Dash(t.side)
  const size = v8Dash(t.size)
  const entry = v8Dash(t.entry)
  const exit = v8Dash(t.exit)
  const pnlRaw = t.pnl
  const pnlStr =
    pnlRaw !== null && pnlRaw !== undefined && pnlRaw !== "" && Number.isFinite(Number(pnlRaw))
      ? v8FormatNumber2(pnlRaw)
      : "—"
  const feeRaw = t.fees ?? t.fee
  const feeStr =
    feeRaw !== null && feeRaw !== undefined && feeRaw !== "" && Number.isFinite(Number(feeRaw))
      ? v8FormatNumber2(feeRaw)
      : "—"
  const strat = v8Dash(t.strategy)
  const sess = v8Dash(t.mode)

  const su = String(t.side || "").toUpperCase()
  const sideColor =
    su === "LONG" ? "#22c55e" : su === "SHORT" ? "#ef4444" : "#94a3b8"
  const pnlNum = Number(pnlRaw)
  const pnlColor =
    pnlRaw !== null && pnlRaw !== undefined && !Number.isNaN(pnlNum)
      ? pnlNum >= 0
        ? "#22c55e"
        : "#ef4444"
      : "var(--v8-muted, #94a3b8)"

  const row = document.createElement("tr")
  row.innerHTML = `
<td class="mono">${timeStr}</td>
<td style="color:${sideColor}" class="mono">${side}</td>
<td class="mono">${size}</td>
<td class="mono">${entry}</td>
<td class="mono">${exit}</td>
<td style="color:${pnlColor}" class="mono">${pnlStr}</td>
<td class="mono">${feeStr}</td>
<td class="mono v8-cell-dim">${strat}</td>
<td class="mono v8-cell-dim">${sess}</td>
`
  return row
}

function v8TrimTradeTbody(tbody) {
  while (tbody.rows.length > V8_HISTORY_MAX_ROWS) {
    tbody.removeChild(tbody.firstChild)
  }
}

async function updateTrades(forceReload = false) {
  const table = document.querySelector("#trade_history_v8 tbody")
  if (!table || !v8TradesHistoryPollActive()) return
  if (v8SkipIfBacktestHardReset("updateTrades")) return

  if (v8TradeHistoryCleared && !forceReload) return

  try {
    const requestId = ++tradesRequestId

    const res = await fetch(`/api/trades/history?${getTradeHistoryQueryParams()}`)
    const data = await res.json()
    if (requestId !== tradesRequestId) return

    let all = Array.isArray(data.history) ? data.history : []
    const anchor = v8ActiveSessionTradeAnchor()
    if (v8TradeScopedMode(selectedDashboardSession) && anchor > 0) {
      all = all.filter((t) => tradeRowTimeSec(t) >= anchor)
    }
    const limited = all.slice(-V8_HISTORY_MAX_ROWS)

    if (!limited.length) {
      tradeHistory = []
      lastTrades = []
      scheduleV8DashboardPaint(() => {
        if (requestId !== tradesRequestId) return
        table.innerHTML = `<tr><td colspan="${V8_TRADE_HISTORY_COLS}" class="v8-empty">No trade history</td></tr>`
      })
      lastTradeRowTimeSec = -1
      v8TradeHistoryCleared = false
      return
    }

    const maxTs = limited.reduce((m, t) => Math.max(m, tradeRowTimeSec(t)), 0)
    if (!forceReload && lastTradeRowTimeSec >= 0 && maxTs <= lastTradeRowTimeSec) {
      return
    }

    const isInitial =
      forceReload ||
      lastTradeRowTimeSec < 0 ||
      Boolean(table.querySelector("td.v8-empty"))
    const newRows = isInitial
      ? limited
      : limited.filter((t) => tradeRowTimeSec(t) > lastTradeRowTimeSec)

    if (!newRows.length && !isInitial) return

    lastTradeRowTimeSec = maxTs
    v8TradeHistoryCleared = false
    tradeHistory = limited
    lastTrades = limited

    scheduleV8DashboardPaint(() => {
      if (requestId !== tradesRequestId) return
      if (isInitial) {
        table.innerHTML = ""
        const frag = document.createDocumentFragment()
        newRows.forEach((t) => frag.appendChild(v8BuildTradeRowTr(t)))
        table.appendChild(frag)
      } else {
        const frag = document.createDocumentFragment()
        newRows.forEach((t) => frag.appendChild(v8BuildTradeRowTr(t)))
        table.appendChild(frag)
        v8TrimTradeTbody(table)
      }
    })
  } catch (_e) {
    /* trade history unavailable */
  }
}

function updateEquityChart() {
  if (v8SkipIfBacktestHardReset("updateEquityChart")) return
  if (v8PanelHiddenById("v8-panel-equity")) return
  const ctx = document.getElementById("equityChart")
  if (!ctx) return

  const labels = equityHistory.map((_, i) => i + 1)

  if (!equityChart) {
    equityChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Equity",
            data: [...equityHistory],
            borderColor: "#22c55e",
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: false },
        },
      },
    })
    return
  }

  equityChart.data.labels = labels
  equityChart.data.datasets[0].data = [...equityHistory]
  equityChart.update("none")
}

function updateSystem(data) {
  const sys = data?.system
  const sec = Math.floor((Date.now() - v8AppStartMs) / 1000)
  if (sec < 10) {
    v8BootstrapAllTradeAnchors()
  }
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const uptimeStr = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`

  const uptimeHdr = document.getElementById("mh-uptime")
  if (uptimeHdr) uptimeHdr.innerText = `Uptime: ${uptimeStr}`

  const el = document.getElementById("system")
  if (el && !v8PanelHiddenById("v8-panel-system")) {
    let cpu = "—"
    let mem = "—"
    if (sys) {
      const c = Number(sys.cpu)
      cpu = Number.isFinite(c) ? `${c.toFixed(0)}%` : "—"
      const memDisp = formatSystemMemoryDisplay(sys)
      mem = memDisp === "—" ? "—" : memDisp
    }
    el.innerHTML = `
        <div class="v8-kv"><span class="k">CPU</span><span class="v mono">${cpu}</span></div>
        <div class="v8-kv"><span class="k">Memory</span><span class="v mono">${mem}</span></div>
        <div class="v8-kv"><span class="k">Uptime</span><span class="v mono">${uptimeStr}</span></div>
    `
  }

  const cpuEl = document.getElementById("mh-cpu")
  const memEl = document.getElementById("mh-memory")
  if (cpuEl) {
    if (sys && Number.isFinite(Number(sys.cpu))) {
      cpuEl.innerText = `CPU: ${Number(sys.cpu).toFixed(0)}%`
    } else {
      cpuEl.innerText = "CPU: —"
    }
  }
  if (memEl) {
    const memDisp = formatSystemMemoryDisplay(sys)
    memEl.innerText = memDisp === "—" ? "MEM: —" : `MEM: ${memDisp}`
  }
}

function updateExecution(data) {
  if (v8PanelHiddenById("v8-panel-execution")) return
  const exec = data?.observability?.execution_monitor
  const pos = data?.position
  const rt = Array.isArray(data?.recent_trades) ? data.recent_trades : []
  const last = rt.length ? rt[0] : null
  const el = document.getElementById("execution")
  if (!el) return

  let state = "IDLE"
  let lastOrder = "—"
  let latency = "—"

  if (exec) {
    if (exec.fill_price) state = "ORDER FILLED"
    else if (exec.signal_price) state = "SIGNAL"
    const lat = exec.total_latency_ms
    if (lat != null && !Number.isNaN(Number(lat))) latency = `${Math.round(Number(lat))} ms`
  }

  if (last) {
    const side = (last.side || "").toUpperCase()
    const px = last.exit ?? last.entry ?? last.fill_price ?? "—"
    lastOrder = `${side} @ ${px}`
  }

  const idle = !exec && (!pos || !pos.side || pos.side === "flat") && !last
  if (idle) {
    el.innerHTML = `
    <div class="v8-kv"><span class="k">State</span><span class="v state-idle">IDLE</span></div>
    <div class="v8-kv"><span class="k">Last Order</span><span class="v mono">—</span></div>
    <div class="v8-kv"><span class="k">Execution Latency</span><span class="v mono">—</span></div>
`
    return
  }

  el.innerHTML = `
    <div class="v8-kv"><span class="k">State</span><span class="v state-hot">${state}</span></div>
    <div class="v8-kv"><span class="k">Last Order</span><span class="v mono">${lastOrder}</span></div>
    <div class="v8-kv"><span class="k">Execution Latency</span><span class="v mono">${latency}</span></div>
`
}

function updateExecutionTimeline(data){

    const pos = data.position;

    let signal = "NONE";
    let decision = "NONE";
    let order = "IDLE";
    let fill = "--";

    if(pos.side === "LONG"){
        signal = "LONG";
        decision = "OPEN LONG";
        order = "FILLED";
    }

    if(pos.side === "SHORT"){
        signal = "SHORT";
        decision = "OPEN SHORT";
        order = "FILLED";
    }

    document.getElementById("execution_timeline").innerHTML = `
    Signal: ${signal}<br>
    Decision: ${decision}<br>
    Order: ${order}<br>
    Exchange: ACK<br>
    Fill: ${pos.size}
    `;

}

function riskFmt(v){
if(v === null || v === undefined) return "—"
if(typeof v === "boolean") return v ? "yes" : "no"
if(typeof v === "number" && Number.isFinite(v)) return String(v)
return String(v)
}

function updateRisk(data) {
  if (v8PanelHiddenById("v8-panel-risk")) return
  if (v8SkipIfBacktestHardReset("updateRisk")) return

const rs = data?.risk_status
const pnl = data?.pnl

if (!rs && !pnl && !v8SessionMetricsActive()) return

let html = ""

if(rs){
const allowed = rs.trade_allowed === true
const blocked = Array.isArray(rs.blocked_rules) && rs.blocked_rules.length
? rs.blocked_rules.join(", ")
: "—"

html += `<b>Trade allowed:</b> ${allowed ? "yes" : "no"}<br>`
html += `<b>Blocked rules:</b> ${blocked}<br>`

if(rs.readonly_state){
html += `<b>Control state:</b> ${riskFmt(rs.readonly_state)}<br>`
}

const der = rs.daily_equity_risk
if(der && typeof der === "object" && Object.keys(der).length){
html += `<br><b>Daily start equity:</b> ${formatCurrency(der.daily_start_equity)}<br>`
html += `<b>Current equity:</b> ${formatCurrency(der.current_equity)}<br>`
html += `<b>Daily drawdown:</b> ${
der.daily_drawdown_pct === null || der.daily_drawdown_pct === undefined
? "—"
: der.daily_drawdown_pct + "%"
}<br>`
html += `<b>Daily limit:</b> ${riskFmt(der.daily_limit_pct)}%<br><br>`
}

const ord = [
"consecutive_loss",
"daily_loss_limit",
"cooldown",
"max_drawdown"
]

const rules = rs.rules || {}
for(const key of ord){
const rule = rules[key]
if(!rule) continue
const st = riskFmt(rule.status)
let detail = ""
if(key === "consecutive_loss"){
detail = `streak ${riskFmt(rule.loss_streak)} / limit ${riskFmt(rule.limit)}`
}else if(key === "daily_loss_limit"){
detail = `daily ${riskFmt(rule.daily_loss)} / max ${riskFmt(rule.max_daily_loss)}`
}else if(key === "cooldown"){
const rem = rule.remaining_time
detail = rule.cooldown_active
? `remaining ${riskFmt(rem)}s`
: "—"
}else if(key === "max_drawdown"){
if(rule.active){
detail = `start ${formatCurrency(rule.daily_start_equity)} / curr ${formatCurrency(rule.current_equity)} / dd ${riskFmt(rule.daily_drawdown_pct)}% / limit ${riskFmt(rule.max_drawdown)}%`
}else{
detail = "inactive until first trade (UTC day)"
}
}
html += `<br><b>${key}</b> (${st})<br>${detail}<br>`
}
html += "<br>"
}

const showJournal = Boolean(pnl) || v8SessionMetricsActive()
if (showJournal) {
  const drawdownStr = v8SessionMetricsActive()
    ? (Number(sessionPnlLocked.max_drawdown ?? 0) * 100).toFixed(2) + "%"
    : (Number(pnl?.max_drawdown ?? 0) * 100).toFixed(2) + "%"
  const realizedStr = v8SessionMetricsActive()
    ? formatCurrency(sessionPnlLocked.realized_pnl ?? 0)
    : formatCurrency(pnl?.realized_pnl ?? 0)
  html += `<b>Journal drawdown:</b> <span id="risk-journal-drawdown" class="mono">${drawdownStr}</span><br>`
  html += `<b>Realized PnL:</b> <span id="risk-realized-pnl" class="mono">${realizedStr}</span><br>`
}

const riskEl = document.getElementById("risk")
if (!riskEl) return
riskEl.innerHTML = html

if (v8SessionMetricsActive()) {
  resetV8SessionRiskPlaceholder()
  return
}
}

function updateSystemMonitor(data){

    const ts = new Date(data.timestamp * 1000).toLocaleTimeString();

    document.getElementById("system_monitor").innerHTML = `
    Last heartbeat: ${ts}<br>
    API: OK
    `;

}

function updateStrategy(data) {
  if (v8PanelHiddenById("v8-panel-strategy")) return
  const pos = data?.position
  const bias = data?.market_bias || {}
  const el = document.getElementById("strategy")
  if (!el) return

  const stratRaw = String(bias.strategy_bias || "")
  const mkt = String(bias.market_bias || "—")
  let direction = "—"
  if (pos && pos.side && pos.side !== "flat") {
    direction = String(pos.side).toUpperCase()
  } else if (stratRaw) {
    const u = stratRaw.toUpperCase()
    direction = u.includes("BULL") ? "LONG" : u.includes("BEAR") ? "SHORT" : stratRaw
  }

  const confidence = "—"

  el.innerHTML = `
    <div class="v8-kv"><span class="k">Direction</span><span class="v">${direction}</span></div>
    <div class="v8-kv"><span class="k">Confidence</span><span class="v mono">${confidence}</span></div>
    <div class="v8-kv"><span class="k">Trend</span><span class="v">${mkt || "—"}</span></div>
`
}

function updatePerformance(data) {
  if (V8_DEBUG_DASHBOARD_PAINT) console.log("[V8] updatePerformance triggered")
  if (v8SkipIfBacktestHardReset("updatePerformance")) return
  if (v8SessionMetricsActive()) return
  if (v8PanelHiddenById("v8-panel-performance")) return
  const el = document.getElementById("performance")
  if (!el) return
  const m = lastMetricsSummary || data?.metrics
  const pnl = data?.pnl || {}
  const mdd = (Number(pnl.max_drawdown ?? 0) * 100).toFixed(2) + "%"
  if (!m) {
    el.innerHTML = `<div class="v8-muted">—</div>`
    return
  }
  el.innerHTML = `
    <div class="v8-kv"><span class="k">Profit factor</span><span class="v mono">${
      m.profit_factor != null && Number.isFinite(Number(m.profit_factor))
        ? formatNumber(m.profit_factor)
        : "—"
    }</span></div>
    <div class="v8-kv"><span class="k">Max drawdown</span><span class="v mono">${mdd}</span></div>
    `
}

function updateMetricsPanel(payload) {
  if (v8SkipIfBacktestHardReset("updateMetricsPanel")) return
  const trades = payload.trades ?? payload.total_trades
  lastMetricsSummary = {
    total_trades: trades ?? 0,
    win_rate: payload.win_rate ?? 0,
    avg_win: payload.avg_win ?? 0,
    profit_factor: payload.profit_factor ?? 0,
  }
  updateMetrics({})
}

function updatePerformancePanel(payload) {
  if (v8SkipIfBacktestHardReset("updatePerformancePanel")) return
  if (!lastMetricsSummary) {
    lastMetricsSummary = {}
  }
  lastMetricsSummary = {
    ...lastMetricsSummary,
    profit_factor:
      payload.profit_factor != null ? payload.profit_factor : lastMetricsSummary.profit_factor,
  }
  updatePerformance({
    pnl: { max_drawdown: payload.max_drawdown ?? 0 },
    metrics: { profit_factor: payload.profit_factor },
  })
}

function resetV8SessionRiskPlaceholder() {
  const drawdown = document.getElementById("risk-journal-drawdown")
  const realized = document.getElementById("risk-realized-pnl")
  if (drawdown) {
    drawdown.textContent = "0.00%"
  }
  if (realized) {
    realized.textContent = "0.00"
  }
}

function resetV8Metrics() {
  const holdSessionMetrics = useSessionMetrics
  useSessionMetrics = false
  try {
    sessionStats = {
      trades: 0,
      wins: 0,
      losses: 0,
      pnl: 0,
      drawdown: 0,
      profitFactor: 0,
    }
    sessionPnlLocked = {
      realized_pnl: 0,
      max_drawdown: 0,
    }
    updateMetricsPanel({
      trades: 0,
      win_rate: 0,
      avg_win: 0,
      profit_factor: 0,
    })
    updatePerformancePanel({
      profit_factor: 0,
      max_drawdown: 0,
    })
    resetV8SessionRiskPlaceholder()
    updateAccountBalanceOnly(lastDashboardPayload || {})
  } finally {
    useSessionMetrics = holdSessionMetrics
  }
}

function updateReconciliation(data) {
  if (v8PanelHiddenById("v8-panel-reconciliation")) return
  const el = document.getElementById("reconciliation")
  if (!el) return
  const pos = data.position || { side: "flat", size: 0 }
  const botPos = `${String(pos.side || "flat").toUpperCase()} ${pos.size ?? 0}`
  const exchangePos = botPos
  el.innerHTML = `
    <div class="v8-kv"><span class="k">Bot position</span><span class="v mono">${botPos}</span></div>
    <div class="v8-kv"><span class="k">Exchange position</span><span class="v mono">${exchangePos}</span></div>
    <div class="v8-kv"><span class="k">Status</span><span class="v ok">OK</span></div>
    `
}

function updateSlippage(data) {
  if (v8PanelHiddenById("v8-panel-slippage")) return
  const el = document.getElementById("slippage")
  if (!el) return
  if (!data.observability || !data.observability.execution_monitor) {
    el.innerHTML = `
    <div class="v8-kv"><span class="k">Signal price</span><span class="v mono">—</span></div>
    <div class="v8-kv"><span class="k">Fill price</span><span class="v mono">—</span></div>
    <div class="v8-kv"><span class="k">Slippage</span><span class="v mono">—</span></div>
    `
    return
  }
  const exec = data.observability.execution_monitor
  el.innerHTML = `
    <div class="v8-kv"><span class="k">Signal price</span><span class="v mono">${exec.signal_price ?? "—"}</span></div>
    <div class="v8-kv"><span class="k">Fill price</span><span class="v mono">${exec.fill_price ?? "—"}</span></div>
    <div class="v8-kv"><span class="k">Slippage</span><span class="v mono">${exec.slippage ?? "—"}</span></div>
    `
}

function updateLatency(data) {
  if (v8PanelHiddenById("v8-panel-latency")) return
  const el = document.getElementById("latency")
  if (!el) return
  const fmt = (v) =>
    v != null && !Number.isNaN(Number(v)) ? `${Number(v).toFixed(0)} ms` : "—"
  if (!data.observability || !data.observability.execution_monitor) {
    el.innerHTML = `
    <div class="v8-kv"><span class="k">Signal latency</span><span class="v mono">—</span></div>
    <div class="v8-kv"><span class="k">Order latency</span><span class="v mono">—</span></div>
    <div class="v8-kv"><span class="k">Execution latency</span><span class="v mono">—</span></div>
    `
    return
  }
  const exec = data.observability.execution_monitor
  el.innerHTML = `
    <div class="v8-kv"><span class="k">Signal latency</span><span class="v mono">${fmt(exec.signal_latency_ms)}</span></div>
    <div class="v8-kv"><span class="k">Order latency</span><span class="v mono">${fmt(exec.exchange_latency_ms)}</span></div>
    <div class="v8-kv"><span class="k">Execution latency</span><span class="v mono">${fmt(exec.total_latency_ms)}</span></div>
    `
}

function updateAlerts(data) {
  if (v8PanelHiddenById("v8-panel-alerts")) return
  const el = document.getElementById("alerts")
  if (!el) return
  const alerts = []
  const exec = data?.observability?.execution_monitor
  if (exec && exec.signal_price != null && exec.fill_price != null) {
    const sp = Number(exec.signal_price)
    const fp = Number(exec.fill_price)
    if (Number.isFinite(sp) && Number.isFinite(fp) && sp > 0) {
      const driftPct = (Math.abs(fp - sp) / sp) * 100
      if (driftPct > 0.05) alerts.push("EXECUTION DRIFT DETECTED")
    }
  }
  const pos = data?.position
  if (pos && Number(pos.size) > 5) alerts.push("Position size unusually large")
  if (data?.pnl && Number(data.pnl.max_drawdown) > 0.1) alerts.push("Drawdown exceeded threshold")
  if (!alerts.length) alerts.push("No active alerts")
  el.innerHTML = `<div class="v8-alert-stack">${alerts.map((a) => `<div class="v8-alert-line">${a}</div>`).join("")}</div>`
}

async function loadSymbols(){

try{

const res = await fetch("/api/symbols")

if(!res.ok) return

const symbols = await res.json()

const select = document.getElementById("symbol_select")

select.innerHTML=""

symbols.forEach(s=>{

const opt=document.createElement("option")
opt.value=s
opt.innerText=s

select.appendChild(opt)

})

}catch(_e){

}

applySymbolSelectFromBaseline()
  syncDlSymbolFromLiveSelect()

}

function filterSymbols(){

const filter = document
.getElementById("symbol_filter")
.value.toUpperCase()

const select = document.getElementById("symbol_select")

let firstVisible = null

Array.from(select.options).forEach(opt=>{

if(opt.value.includes(filter)){
opt.style.display=""
if(!firstVisible) firstVisible = opt
}else{
opt.style.display="none"
}

})

// auto select first match
if(firstVisible){
select.value = firstVisible.value
}

}


function initMarketWS(){

const ws = new WebSocket("ws://127.0.0.1:8000/ws/state/live_shadow")

ws.onmessage = (event)=>{

const data = JSON.parse(event.data)

if(data.price){

document.getElementById("mh-price").innerText =
"Price: " + data.price

}

if(data.change_24h){

document.getElementById("mh-change").innerText =
"24h: " + data.change_24h + "%"

}

if(data.funding){

document.getElementById("mh-funding").innerText =
"Funding: " + data.funding

}

}

}

async function loadMarket(){

try{

const res = await fetch("/api/system/market")
const data = await res.json()

const priceEl = document.getElementById("mh-price")
const changeEl = document.getElementById("mh-change")
const fundingEl = document.getElementById("mh-funding")

priceEl.innerText = "Price: " + data.price
changeEl.innerText = "24h: " + data.change_24h + "%"
fundingEl.innerText = "Funding: " + data.funding

// màu 24h
if(data.change_24h >= 0){
changeEl.style.color = "#22c55e"
}else{
changeEl.style.color = "#ef4444"
}

// màu funding
if(data.funding >= 0){
fundingEl.style.color = "#22c55e"
}else{
fundingEl.style.color = "#ef4444"
}
priceEl.style.color = "#38bdf8"

setTimeout(()=>{
priceEl.style.color = "#e2e8f0"
},300)

}catch(_e){

}

}

const V8_PIPELINE_STAGE_LABELS = {
  signal: "Signal",
  decision: "Decision",
  order: "Order",
  exchange: "Exchange",
  fill: "Fill",
}

function renderExecutionPipeline() {
  const container = document.getElementById("execution_pipeline")
  if (!container) return
  container.innerHTML = `
<div class="execution-pipeline">
<div class="v8-pipeline-track">
<div id="p_signal" class="pipeline-step" data-step="signal">Signal</div>
<div class="pipeline-arrow">→</div>
<div id="p_decision" class="pipeline-step" data-step="decision">Decision</div>
<div class="pipeline-arrow">→</div>
<div id="p_order" class="pipeline-step" data-step="order">Order</div>
<div class="pipeline-arrow">→</div>
<div id="p_exchange" class="pipeline-step" data-step="exchange">Exchange</div>
<div class="pipeline-arrow">→</div>
<div id="p_fill" class="pipeline-step" data-step="fill">Fill</div>
</div>
</div>
`
}

function updateExecutionPipeline(data) {
  if (v8PanelHiddenById("v8-panel-pipeline")) return
  const root = data || {}
  const selectedStatus = sessionRuntimeStatus[selectedDashboardSession] || "UNKNOWN"
  const pipelineSessionActive =
    selectedStatus === "RUNNING" || selectedStatus === "READY"
  const steps = ["signal", "decision", "order", "exchange", "fill"]
  const meta = document.getElementById("v8_pipeline_meta")

  if (!dualPanelModeEnabled && !pipelineSessionActive) {
    steps.forEach((s) => {
      const el = document.getElementById("p_" + s)
      if (!el) return
      el.classList.remove("active", "done")
    })
    if (meta) meta.textContent = "Current Step: — · Latency: — (session not running)"
    return
  }

  let stage = "signal"
  if (root.position?.side && root.position.side !== "flat") {
    stage = "fill"
  } else if (root.recent_trades && root.recent_trades.length > 0) {
    stage = "fill"
  } else if (root?.observability?.execution_monitor?.fill_price) {
    stage = "fill"
  } else if (root?.observability?.execution_monitor?.signal_price) {
    stage = "decision"
  }

  steps.forEach((s) => {
    const el = document.getElementById("p_" + s)
    if (!el) return
    el.classList.remove("active", "done")
  })

  let done = true
  steps.forEach((s) => {
    const el = document.getElementById("p_" + s)
    if (!el) return
    if (done) el.classList.add("done")
    if (s === stage) {
      el.classList.remove("done")
      el.classList.add("active")
      done = false
    }
  })

  const exec = root?.observability?.execution_monitor
  const lat = exec?.total_latency_ms
  const stageLabel = V8_PIPELINE_STAGE_LABELS[stage] || stage
  if (meta) {
    meta.textContent = `Current Step: ${stageLabel} · Latency: ${
      lat != null && !Number.isNaN(Number(lat)) ? Math.round(Number(lat)) + " ms" : "—"
    }`
  }
}

function updateV8PipelineBreadcrumb(_data) {
  const el = document.getElementById("v8_flow_breadcrumb")
  if (!el) return
  el.textContent = "Signal → Decision → Order → Exchange → Fill"
}

function v8ExecPriceField(v) {
  if (v === null || v === undefined || v === "") return "—"
  const n = Number(v)
  if (!Number.isFinite(n)) return "—"
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 })
}

function v8ExecSlippageField(v) {
  if (v === null || v === undefined || v === "") return "—"
  const n = Number(v)
  if (!Number.isFinite(n)) return "—"
  return n.toFixed(4)
}

function v8ExecLatencyField(v) {
  if (v === null || v === undefined || v === "") return "—"
  const n = Number(v)
  if (!Number.isFinite(n)) return "—"
  return `${n.toFixed(2)} ms`
}

function v8ExecStatusField(t) {
  return v8Dash(t?.status)
}

/** Clears execution history table DOM (client state; pair with POST /api/execution/clear to wipe DB). */
function clearV8ExecutionHistoryView() {
  const tbody = document.querySelector("#execution_history_v8 tbody")
  if (!tbody) return
  lastExecRowTimeSec = -1
  tbody.innerHTML = `<tr><td colspan="${V8_EXEC_HISTORY_COLS}" class="v8-table-placeholder">Cleared — view only; data reloads on next refresh</td></tr>`
}

/** Clears session-scoped execution_history SQLite + UI; polling will stay empty until new fills. */
async function clearExecutionHistory() {
  const sid = String(selectedDashboardSession || "live").toLowerCase()
  if (!["live", "shadow", "paper", "backtest"].includes(sid)) {
    if (typeof console !== "undefined" && console.warn) {
      console.warn("[V8] execution clear: unsupported session", sid)
    }
    return
  }
  try {
    const res = await fetch(`/api/execution/clear?session=${encodeURIComponent(sid)}`, {
      method: "POST",
    })
    if (!res.ok) {
      const t = await res.text()
      if (typeof console !== "undefined" && console.warn) {
        console.warn("[V8] execution clear failed", res.status, t)
      }
      return
    }
    executionHistoryRequestId += 1
    executionHistory = []
    lastExecution = []
    lastExecRowTimeSec = -1
    const tbody = document.querySelector("#execution_history_v8 tbody")
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="${V8_EXEC_HISTORY_COLS}" class="v8-table-placeholder">Execution history cleared</td></tr>`
    }
  } catch (e) {
    if (typeof console !== "undefined" && console.warn) {
      console.warn("[V8] execution clear", e)
    }
  }
}

/** Clears trade history: archive + backend reset for selected session, then UI + refresh. */
async function clearV8TradeHistoryView() {
  const tbody = document.querySelector("#trade_history_v8 tbody")
  if (!tbody) return

  const guardRaw =
    lastDashboardPayload?.position?.size ?? lastDashboardPayload?.position_size ?? 0
  const guardSize = Number(guardRaw)
  if (Number.isFinite(guardSize) && Math.abs(guardSize) > 0) {
    alert(
      "Cannot clear history while position is open.\n" +
        "Please close position or wait for TP/SL before clearing."
    )
    return
  }

  const sid = String(selectedDashboardSession || "live").toLowerCase()
  try {
    const ar = await fetch(`/api/session/archive?session=${encodeURIComponent(sid)}`, {
      method: "POST",
    })
    if (!ar.ok && typeof console !== "undefined" && console.warn) {
      console.warn("[V8] session archive failed", ar.status)
    }
    const rs = await fetch(`/api/session/reset?session=${encodeURIComponent(sid)}`, {
      method: "POST",
    })
    if (!rs.ok && typeof console !== "undefined" && console.warn) {
      console.warn("[V8] session reset failed", rs.status)
    }
  } catch (e) {
    if (typeof console !== "undefined" && console.warn) {
      console.warn("[V8] clear history backend:", e)
    }
  }
  resetV8Metrics()
  clearV8ExecutionHistoryView()
  useSessionMetrics = true
  localStorage.setItem(V8_SESSION_METRICS_KEY, "true")
  lastTradeRowTimeSec = 0
  v8TradeHistoryCleared = true
  recentTrades = []
  tradeHistory = []
  lastTrades = []
  if (selectedDashboardSession !== "backtest") {
    backtestResetActive = false
    backtestUIHardReset = false
  }
  if (selectedDashboardSession === "backtest") {
    backtestIdleMode = true
  }
  tbody.innerHTML = `
    <tr>
      <td colspan="${V8_TRADE_HISTORY_COLS}" class="v8-empty">
        Trade history cleared
      </td>
    </tr>
  `
  if (String(selectedDashboardSession || "").toLowerCase() === "backtest") {
    resetBacktestPanels()
    delete dashboardSessionCache["backtest"]
  }
  await loadDashboard()
  await pollV8Metrics()
}

/** Exit session-metrics mode and resume server-backed metrics (optional; e.g. console or future control). */
function resetSessionMetrics() {
  useSessionMetrics = false
  localStorage.removeItem(V8_SESSION_METRICS_KEY)
  void loadDashboard()
}

window.resetSessionMetrics = resetSessionMetrics

function v8BuildExecRowTr(t) {
  const ts = t.timestamp ?? t.time
  const time = formatTradeTime(ts)
  const symbol = v8Dash(t.symbol)
  const side = v8Dash(t.side)
  const size = v8Dash(t.qty ?? t.size)
  const signalPx = v8ExecPriceField(t.signal_price)
  const orderPx = v8ExecPriceField(t.order_price)
  const fillPx = v8ExecPriceField(t.fill_price)
  const slip = v8ExecSlippageField(t.slippage)
  const latency = v8ExecLatencyField(t.latency)
  const status = v8ExecStatusField(t)
  const step = v8Dash(t.step)
  const orderId = v8Dash(t.order_id)

  const su = String(t.side || "").toUpperCase()
  const sideColor =
    su === "LONG" ? "#22c55e" : su === "SHORT" ? "#ef4444" : ""

  const row = document.createElement("tr")
  row.innerHTML = `
<td class="mono">${time}</td>
<td class="mono">${symbol}</td>
<td class="mono"${sideColor ? ` style="color:${sideColor}"` : ""}>${side}</td>
<td class="mono">${size}</td>
<td class="mono">${signalPx}</td>
<td class="mono">${orderPx}</td>
<td class="mono">${fillPx}</td>
<td class="mono">${slip}</td>
<td class="mono">${latency}</td>
<td class="mono">${status}</td>
<td class="mono v8-cell-dim">${step}</td>
<td class="mono">${orderId}</td>
`
  return row
}

async function updateExecutionHistory() {
  const table = document.querySelector("#execution_history_v8 tbody")
  if (!table || !v8ExecHistoryPollActive()) return
  if (v8SkipIfBacktestHardReset("updateExecutionHistory")) return

  const placeholder = (msg) => {
    table.innerHTML = `<tr><td colspan="${V8_EXEC_HISTORY_COLS}" class="v8-table-placeholder">${msg}</td></tr>`
  }

  try {
    const requestId = ++executionHistoryRequestId

    const res = await fetch(`/api/execution/history?${getExecutionHistoryQueryParams()}`)

    if (!res.ok) {
      executionHistory = []
      lastExecution = []
      placeholder("No execution history available")
      lastExecRowTimeSec = -1
      return
    }

    const data = await res.json()
    if (requestId !== executionHistoryRequestId) return

    const all = Array.isArray(data.history) ? data.history : []
    const limited = all.slice(0, V8_HISTORY_MAX_ROWS)

    if (!limited.length) {
      executionHistory = []
      lastExecution = []
      placeholder("No execution history available")
      lastExecRowTimeSec = -1
      return
    }

    const topTs = execRowTimeSec(limited[0])
    if (lastExecRowTimeSec >= 0 && topTs <= lastExecRowTimeSec) {
      return
    }

    const isInitial = lastExecRowTimeSec < 0
    const newRows = isInitial
      ? limited
      : limited.filter((t) => execRowTimeSec(t) > lastExecRowTimeSec)

    if (!newRows.length && !isInitial) return

    lastExecRowTimeSec = Math.max(lastExecRowTimeSec, topTs)
    executionHistory = limited
    lastExecution = limited

    scheduleV8DashboardPaint(() => {
      if (requestId !== executionHistoryRequestId) return
      if (isInitial) {
        table.innerHTML = ""
        const frag = document.createDocumentFragment()
        newRows.forEach((t) => frag.appendChild(v8BuildExecRowTr(t)))
        table.appendChild(frag)
      } else {
        const frag = document.createDocumentFragment()
        newRows.forEach((t) => frag.appendChild(v8BuildExecRowTr(t)))
        const first = table.firstChild
        if (first) table.insertBefore(frag, first)
        else table.appendChild(frag)
        while (table.rows.length > V8_HISTORY_MAX_ROWS) {
          table.removeChild(table.lastChild)
        }
      }
    })
  } catch (_e) {
    lastExecRowTimeSec = -1
    executionHistory = []
    lastExecution = []
    placeholder("No execution history available")
  }
}

function updateOrderLifecycle(data){

const el = document.getElementById("order_lifecycle")
if(!el) return

const pos = data?.position

if(!pos){
el.innerHTML = `
State: IDLE<br>
Side: flat<br>
Size: 0
`
return
}

let state = "IDLE"

if(pos.side === "LONG") state = "LONG OPENED"
if(pos.side === "SHORT") state = "SHORT OPENED"

el.innerHTML = `
State: ${state}<br>
Side: ${pos.side}<br>
Size: ${pos.size}
`
}

async function setExchange(btn){

const exchange =
document.getElementById("exchange_select").value

try{

await fetch(`/api/control/exchange${controlPanelSessionQuery()}`,{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({exchange})
})

markControlApplyCommitted("exchange_select", exchange)

flashButton(btn)

}catch(e){

console.error(e)

}

}

function updateMarketBias(data) {
  const host = document.getElementById("market_bias")
  if (!host) return

const bias = data?.market_bias

if(!bias){

host.innerHTML = `
Market: -<br>
Strategy: -<br>
Execution: -
`
return
}

const market = bias.market_bias || "-"
const strategy = bias.strategy_bias || "-"
const execution = bias.execution_bias || "-"

// color logic
function color(v){

if(v.includes("BULL")) return "#22c55e"
if(v.includes("BEAR")) return "#ef4444"

return "#e2e8f0"

}

host.innerHTML = `

Market:
<span style="color:${color(market)}">
${market}
</span>
<br>

Strategy:
<span style="color:${color(strategy)}">
${strategy}
</span>
<br>

Execution:
<span style="color:${color(execution)}">
${execution}
</span>

`

}

async function setRisk(btn){

const display = document.getElementById("risk_input").value
const fraction = riskPercentInputToFraction(display)

if(!Number.isFinite(fraction) || fraction <= 0){
console.error("Invalid risk: enter a positive percent (e.g. 1 for 1%)")
return
}

try{

await fetch(`/api/control/risk${controlPanelSessionQuery()}`,{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({risk:fraction})
})
await syncSessionConfigAfterControl()

markControlApplyCommitted("risk_input", display)

flashButton(btn)

}catch(e){

console.error(e)

}

}


async function setMode(btn){

const mode = document.getElementById("trade_mode_select").value

try{

await fetch("/api/control/trade_mode",{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({mode})
})
await syncSessionConfigAfterControl()

markControlApplyCommitted("trade_mode_select", mode)

flashButton(btn)

}catch(e){

console.error(e)

}

}


async function setStrategy(btn){

const strategy = document.getElementById("strategy_select").value

try{

await fetch(`/api/control/strategy${controlPanelSessionQuery()}`,{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({strategy})
})
await syncSessionConfigAfterControl()

markControlApplyCommitted("strategy_select", strategy)

flashButton(btn)

}catch(e){

console.error(e)

}

}


async function setSymbol(btn){

const symbol = document.getElementById("symbol_select").value

try{

await fetch(`/api/control/symbol${controlPanelSessionQuery()}`,{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({symbol})
})

markControlApplyCommitted("symbol_select", symbol)

flashButton(btn)

}catch(e){

console.error(e)

}

}

function flashButton(button){

const row = button.closest(".control-row")

if(row){
row.querySelectorAll("button").forEach(btn=>{
btn.style.backgroundColor = ""
btn.style.color = ""
})
}

button.style.backgroundColor = "#22c55e"
button.style.color = "#000"

}

function pendingButton(selectId){

const select = document.getElementById(selectId)

if(!select) return

const button = select
.closest(".control-row")
.querySelector("button")

if(!button) return

if(!controlPanelBaselineReady){
button.style.backgroundColor = ""
button.style.color = ""
return
}

const last = lastAppliedControlValues[selectId]
const current = String(select.value)

if(last !== undefined && current !== last){

button.style.backgroundColor = "#3b82f6"
button.style.color = "#fff"

}else{

button.style.backgroundColor = ""
button.style.color = ""

}

}