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
let dualPanelModeEnabled = false
let dashboardRequestId = 0
let tradesRequestId = 0
let executionHistoryRequestId = 0
const sessionRuntimeStatus = {
  live: "UNKNOWN",
  shadow: "UNKNOWN",
}

function sessionControlStatus(msg, isError = false) {
  const el = document.getElementById("session_control_status")
  if (!el) return
  el.textContent = msg || ""
  el.style.color = isError ? "#f87171" : "#cbd5e1"
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
    const res = await fetch(
      `/api/debug/export-candle?session=${encodeURIComponent(sid)}`
    )
    const data = await res.json()
    if (data.ok) {
      console.log("[EXPORT]", data)
      console.log(`[CANDLE EXPORT] ${sid} ${data.rows} bars`)
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

async function refreshAllPanels() {
  await loadDashboard()
  await updateTrades()
  await updateExecutionHistory()

  const qp = getSessionQueryParams()
  try {
    const [position, pnl, risk] = await Promise.all([
      fetchJsonSafe(`/api/dashboard/position?${qp}`),
      fetchJsonSafe(`/api/dashboard/pnl?${qp}`),
      fetchJsonSafe(`/api/dashboard/risk-status?${qp}`),
    ])

    updatePosition({ position })
    updatePnL({ pnl })
    updateRisk({ risk_status: risk, pnl })
  } catch (e) {
    console.log("refreshAllPanels partial refresh error", e)
  }
}

async function refreshAfterLifecycleAction() {
  await refreshAllPanels()
  // Post-lifecycle state can settle asynchronously; perform short retries.
  for (let i = 0; i < 2; i++) {
    await new Promise((resolve) => setTimeout(resolve, 600))
    await refreshAllPanels()
  }
}

function normalizeSessionStatus(value) {
  const s = String(value || "").trim().toUpperCase()
  if (s === "RUNNING") return "RUNNING"
  if (s === "STOPPED" || s === "IDLE" || s === "CREATED") return "STOPPED"
  return "UNKNOWN"
}

function setSessionStatusEl(id, status) {
  const el = document.getElementById(id)
  if (!el) return
  const text = normalizeSessionStatus(status)
  el.textContent = text
  if (id === "session_status_live") sessionRuntimeStatus.live = text
  if (id === "session_status_shadow") sessionRuntimeStatus.shadow = text
  el.classList.remove("running", "stopped", "unknown")
  if (text === "RUNNING") el.classList.add("running")
  else if (text === "STOPPED") el.classList.add("stopped")
  else el.classList.add("unknown")
}

function readStatusFromSessionsPayload(payload, sessionId) {
  if (!payload) return "UNKNOWN"
  if (Array.isArray(payload)) {
    const row = payload.find((x) => String(x?.id || x?.session_id || "").toLowerCase() === sessionId)
    return row?.status || "UNKNOWN"
  }
  if (Array.isArray(payload.sessions)) {
    const row = payload.sessions.find((x) => String(x?.id || x?.session_id || "").toLowerCase() === sessionId)
    return row?.status || "UNKNOWN"
  }
  if (payload.sessions && typeof payload.sessions === "object") {
    const row = payload.sessions[sessionId]
    if (row && typeof row === "object") return row.status || "UNKNOWN"
    if (typeof row === "string") return row
  }
  if (payload[sessionId] && typeof payload[sessionId] === "object") {
    return payload[sessionId].status || "UNKNOWN"
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
  } catch (_e) {
    setSessionStatusEl("session_status_live", "UNKNOWN")
    setSessionStatusEl("session_status_shadow", "UNKNOWN")
  }
}

function getSessionQueryParams() {
  const params = new URLSearchParams()
  params.set("session", selectedDashboardSession)
  if (dualPanelModeEnabled) {
    params.set("dual", "1")
  }
  return params.toString()
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
}

async function onSessionSelectionChanged() {
  const select = document.getElementById("session_select")
  const dual = document.getElementById("dual_panel_toggle")
  selectedDashboardSession = select ? String(select.value || "live").toLowerCase() : "live"
  dualPanelModeEnabled = dual ? dual.checked === true : false
  localStorage.setItem("dashboard-session", selectedDashboardSession)
  localStorage.setItem("dashboard-dual-panel", dualPanelModeEnabled ? "1" : "0")
  await loadDashboard()
  await updateTrades()
  await updateExecutionHistory()
}

function markControlApplyCommitted(elementId, value) {
  skipNextControlPanelRefresh = true
  lastAppliedControlValues[elementId] = String(value)
}

function syncControlLastAppliedFromConfig(config) {
  if (!config) return
  const pairs = [
    ["trade_mode_select", "trade_mode"],
    ["trading_mode_select", "mode"],
    ["strategy_select", "strategy"],
    ["exchange_select", "exchange"],
    ["symbol_select", "symbol"],
    ["risk_input", "risk_percent"],
  ]
  for (const [elementId, configKey] of pairs) {
    const v = config[configKey]
    if (configKey === "risk_percent") {
      if (v !== undefined && v !== null && !Number.isNaN(Number(v))) {
        lastAppliedControlValues[elementId] = String(v)
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
  "trade_mode_select",
  "trading_mode_select",
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

  // INIT GRIDSTACK
  grid = GridStack.init({
    column:12,
    cellHeight:80,
    margin:1,
    float:true,
    draggable:{handle:'.card-header'},
    resizable:{handles:'se'}
  })

  restoreLayout()
  restoreHiddenPanels()

  // SAVE LAYOUT
  grid.on("change", function () {
    const layout = grid.save()
    localStorage.setItem("gridstack-layout", JSON.stringify(layout))
  })

  // Symbol list must exist before hydrating from /api/dashboard (avoids race → false “pending”).
  ;(async function bootstrapDashboardControlPanel() {
    hydrateSessionSelectorFromStorage()
    await loadSymbols()
    await loadDashboard()
    await updateTrades()
    await updateExecutionHistory()
  })()

  // nếu bạn CHƯA chuyển hẳn sang WebSocket thì giữ polling
  setInterval(loadDashboard,3000)
  setInterval(updateTrades,3000)
  setInterval(updateExecutionHistory,5000)

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
})

function restoreLayout(){

const saved = JSON.parse(
localStorage.getItem("gridstack-layout")
)

if(!saved){
grid.compact()
return
}

saved.forEach(node => {

const el = document.querySelector(
`[gs-id="${node.id}"]`
)

if(el){

grid.update(el,{
x:node.x,
y:node.y,
w:node.w,
h:node.h
})

}

})

grid.compact()

}

grid?.on("change",function(){
const layout = grid.save()
localStorage.setItem("gridstack-layout",JSON.stringify(layout))
})

async function loadDashboard(){

try{
const requestId = ++dashboardRequestId
await refreshSessionStatuses()

const res = await fetch(`/api/dashboard?${getSessionQueryParams()}`)

if(!res.ok) return

const data = await res.json()
if(requestId !== dashboardRequestId) return
console.log("dashboard data:",data)

if(!data) return

updatePosition(data)
updatePnL(data)
//updateMetrics(data)
updateTrades()

updateSystem(data)
updateExecution(data)
//updateExecutionTimeline(data)
updateRisk(data)
//updateReconciliation(data)

//updateSystemMonitor(data)
updateStrategy(data)
updateMarketBias(data)
// Restore Pause / Resume
if(data.config){

syncControlLastAppliedFromConfig(data.config)

const paused = data.config.trading_enabled === false

if(paused){

document.getElementById("pause_btn").style.background = "#ef4444"
document.getElementById("pause_btn").style.color = "#fff"

document.getElementById("resume_btn").style.background = ""
document.getElementById("resume_btn").style.color = ""

}else{

document.getElementById("resume_btn").style.background = "#22c55e"
document.getElementById("resume_btn").style.color = "#000"

document.getElementById("pause_btn").style.background = ""
document.getElementById("pause_btn").style.color = ""

}

}
// Restore Control Panel
if(data.config && !controlInitialized){

// Trade Mode
if(data.config.trade_mode){

document.getElementById("trade_mode_select").value =
data.config.trade_mode

flashButton(
document.querySelector("#trade_mode_select")
.closest(".control-row")
.querySelector("button")
)

}

// Strategy
if(data.config.strategy){

document.getElementById("strategy_select").value =
data.config.strategy

flashButton(
document.querySelector("#strategy_select")
.closest(".control-row")
.querySelector("button")
)

}

// Trading Mode
if(data.config.mode){

document.getElementById("trading_mode_select").value =
data.config.mode

flashButton(
document.querySelector("#trading_mode_select")
.closest(".control-row")
.querySelector("button")
)

}

// Exchange
if(data.config.exchange){

document.getElementById("exchange_select").value =
data.config.exchange

flashButton(
document.querySelector("#exchange_select")
.closest(".control-row")
.querySelector("button")
)

}

// Symbol
if(data.config.symbol){

document.getElementById("symbol_select").value =
data.config.symbol

flashButton(
document.querySelector("#symbol_select")
.closest(".control-row")
.querySelector("button")
)

}

// Risk (0 is valid — do not use truthy check)
if(data.config.risk_percent !== undefined && data.config.risk_percent !== null
&& !Number.isNaN(Number(data.config.risk_percent))){

document.getElementById("risk_input").value =
data.config.risk_percent

flashButton(
document.querySelector("#risk_input")
.closest(".control-row")
.querySelector("button")
)

}

applySymbolSelectFromBaseline()

controlInitialized = true
controlPanelBaselineReady = true
refreshControlApplyButtonStates()

} else if (data.config && controlInitialized && controlPanelBaselineReady) {

refreshControlApplyButtonStates()

}
//updatePerformance(data)

updateSlippage(data)
updateLatency(data)
updateAlerts(data)
updateExecutionPipeline(data)
updateExecutionHistory()
updateOrderLifecycle(data)

}catch(e){

console.log("dashboard error", e)

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

ws.onopen = () => {
console.log("WS connected")
}

ws.onmessage = (event) => {

const msg = JSON.parse(event.data)

// websocket của bạn đôi khi có {type, data}
const data = msg.data || msg

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

// PNL + risk rule status (risk_status may arrive without pnl)
if(data.pnl){
updatePnL(data)
}
if(data.pnl || data.risk_status){
updateRisk(data)
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

}
}

function updatePosition(data){

    const p = data?.position;

    if(!p){
        document.getElementById("position").innerHTML = `
            Side: flat<br>
            Size: 0
        `;
        return;
    }

    document.getElementById("position").innerHTML = `
        Side: ${p.side}<br>
        Size: ${p.size}
    `;

}

function pnlFmtNum(v){
if(v === null || v === undefined || Number.isNaN(Number(v))) return "—"
return Number(v).toFixed(2)
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

function updatePnL(data){

const pnl = data?.pnl
if(!pnl) return

const realized = Number(pnl.realized_pnl ?? 0).toFixed(2)
const drawdown =
(Number(pnl.max_drawdown ?? 0) * 100).toFixed(2) + "%"

const panels = Array.isArray(pnl.panels) ? pnl.panels : []
let body = ""

if(panels.length === 0){
const legacy = {
mode: pnl.mode,
symbol: pnl.symbol,
quote_asset: pnl.quote_asset,
equity: pnl.equity,
floating: pnl.floating_pnl,
total_equity: pnl.total_equity
}
body = pnlRenderOnePanel(legacy, pnl)
}else if(panels.length === 1){
body = pnlRenderOnePanel(panels[0], pnl)
}else{
body = panels.map((p, i) => {
const title = pnlFmtStr(p?.mode, "—")
const block = pnlRenderOnePanel(p, pnl)
return `<div style="margin-bottom:6px"><b>${title}</b><br>${block}</div>`
}).join("<hr style=\"border:none;border-top:1px solid #333;margin:8px 0\">")
}

document.getElementById("pnl").innerHTML = `
${body}
Realized PnL: ${realized}<br>
Drawdown: ${drawdown}
`

if(pnl.session_status === "single" && pnl.total_equity != null){
equityHistory.push(Number(pnl.total_equity))
}

if(equityHistory.length > 50){
equityHistory.shift()
}

updateEquityChart()
}

function updateMetrics(data){

    const m = data.metrics;

    document.getElementById("metrics").innerHTML = `
        Trades: ${m.total_trades}<br>
        Win Rate: ${(m.win_rate*100).toFixed(2)} %<br>
        Avg Win: ${m.avg_win}<br>
        Avg Loss: ${m.avg_loss}
    `;

}

async function updateTrades(){

const table = document.querySelector("#trades tbody")

if(!table) return

try{
const requestId = ++tradesRequestId

const res = await fetch(`/api/trades/history?${getTradeHistoryQueryParams()}`)
const data = await res.json()
if(requestId !== tradesRequestId) return

table.innerHTML=""

if(!data.history) return

data.history.forEach(t=>{

const time = new Date(t.time*1000).toLocaleString()

const side = t.side ?? "-"
const size = t.size ?? "-"
const entry = t.entry ?? "-"
const exit = t.exit ?? "-"
const pnl = t.pnl ?? 0
const fees = Number(t.fees ?? t.fee ?? 0).toFixed(3)

const sideColor = side==="LONG" ? "#22c55e" : "#ef4444"
const pnlColor = pnl>=0 ? "#22c55e" : "#ef4444"

const row=document.createElement("tr")

row.innerHTML=`

<td>${time}</td>
<td>${t.mode ?? "-"}</td>
<td>${t.symbol ?? "-"}</td>
<td>${t.strategy ?? "-"}</td>
<td style="color:${sideColor}">${side}</td>
<td>${size}</td>
<td>${entry}</td>
<td>${exit}</td>
<td style="color:${pnlColor}">${pnl}</td>
<td>${fees}</td>
<td>${t.asset || "USDT"}</td>

`

table.appendChild(row)

})

}catch(e){

console.log("trade history error",e)

}

}

function updateEquityChart(){

const labels = equityHistory.map((_,i)=>i+1);

const ctx = document.getElementById("equityChart");

if(!equityChart){

equityChart = new Chart(ctx,{
type:"line",
data:{
labels:labels,
datasets:[{
label:"Equity",
data:equityHistory,
borderColor:"#22c55e",
fill:false
}]
},
options:{
responsive:true,
plugins:{
legend:{
display:false
}
}
}
});

}else{

equityChart.data.labels = labels;
equityChart.data.datasets[0].data = equityHistory;
equityChart.update();

}

}

function updateSystem(data){

const uptime = new Date().toLocaleTimeString();

document.getElementById("system").innerHTML = `
Last Update: ${uptime}
`;

if(data.system){

document.getElementById("mh-cpu").innerText =
"CPU: " + data.system.cpu + "%"

document.getElementById("mh-mem").innerText =
"MEM: " + data.system.mem_mb.toFixed(1) + " MB"

}

}

function updateExecution(data){

const exec = data?.observability?.execution_monitor
const pos = data?.position

// Nếu không có execution hoặc position flat → reset
if(!exec || !pos || !pos.side || pos.side === "flat"){

document.getElementById("execution").innerHTML = `
State: IDLE<br>
Side: -<br>
Size: -
`

return
}

let state = "IDLE"

if(exec.fill_price){
state = "FILLED"
}
else if(exec.signal_price){
state = "SIGNAL"
}

const side = exec.side ?? "-"
const size = exec.size ?? "-"

document.getElementById("execution").innerHTML = `
State: ${state}<br>
Side: ${side}<br>
Size: ${size}
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

function updateRisk(data){

const rs = data?.risk_status
const pnl = data?.pnl

if(!rs && !pnl) return

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
html += `<br><b>Daily start equity:</b> ${riskFmt(der.daily_start_equity)}<br>`
html += `<b>Current equity:</b> ${riskFmt(der.current_equity)}<br>`
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
detail = `start ${riskFmt(rule.daily_start_equity)} / curr ${riskFmt(rule.current_equity)} / dd ${riskFmt(rule.daily_drawdown_pct)}% / limit ${riskFmt(rule.max_drawdown)}%`
}else{
detail = "inactive until first trade (UTC day)"
}
}
html += `<br><b>${key}</b> (${st})<br>${detail}<br>`
}
html += "<br>"
}

if(pnl){
const drawdown = (Number(pnl.max_drawdown ?? 0) * 100).toFixed(2) + "%"
const realized = Number(pnl.realized_pnl ?? 0).toFixed(2)
html += `<b>Journal drawdown:</b> ${drawdown}<br>`
html += `<b>Realized PnL:</b> ${realized}<br>`
}

document.getElementById("risk").innerHTML = html
}

function updateSystemMonitor(data){

    const ts = new Date(data.timestamp * 1000).toLocaleTimeString();

    document.getElementById("system_monitor").innerHTML = `
    Last heartbeat: ${ts}<br>
    API: OK
    `;

}

function updateStrategy(data){

const pos = data?.position

if(!pos){
document.getElementById("strategy").innerHTML = `
Strategy State: NO POSITION<br>
Side: FLAT<br>
Position Size: 0
`
return
}

let state = "NO POSITION"

const side = (pos.side || "").toUpperCase()

if(side === "LONG") state = "LONG ACTIVE"
if(side === "SHORT") state = "SHORT ACTIVE"

document.getElementById("strategy").innerHTML = `
Strategy State: ${state}<br>
Side: ${side || "-"}<br>
Position Size: ${pos.size ?? 0}
`

}

function updatePerformance(data){

    const m = data.metrics;

    document.getElementById("performance").innerHTML = `
    Profit Factor: ${m.profit_factor ?? "N/A"}<br>
    Avg Win: ${m.avg_win}<br>
    Avg Loss: ${m.avg_loss}
    `;

}

function updateReconciliation(data){

    const pos = data.position;

    const botPos = pos.side + " " + pos.size;

    const exchangePos = pos.side + " " + pos.size;

    let status = "OK";

    document.getElementById("reconciliation").innerHTML = `
    Bot Position: ${botPos}<br>
    Exchange Position: ${exchangePos}<br>
    Status: ${status}
    `;

}

function updateSlippage(data){

    if(
        !data.observability ||
        !data.observability.execution_monitor
    ) return;

    const exec = data.observability.execution_monitor;

    document.getElementById("slippage").innerHTML = `
    Signal Price: ${exec.signal_price ?? "-"}<br>
    Fill Price: ${exec.fill_price ?? "-"}<br>
    Slippage: ${exec.slippage ?? "-"}
    `;
}

function updateLatency(data){

    if(
        !data.observability ||
        !data.observability.execution_monitor
    ) return;

    const exec = data.observability.execution_monitor;

    const fmt = v => v ? v.toFixed(2) : "-";

    document.getElementById("latency").innerHTML = `
    Signal → Order: ${fmt(exec.signal_latency_ms)} ms<br>
    Order → Exchange: ${fmt(exec.exchange_latency_ms)} ms<br>
    Exchange → Fill: ${fmt(exec.fill_latency_ms)} ms<br>
    Total Latency: ${fmt(exec.total_latency_ms)} ms
    `;
}

function updateAlerts(data){

    const pos = data.position;

    let alerts = [];

    if(pos.size > 5){
        alerts.push("⚠ Position size unusually large");
    }

    if(data.pnl.max_drawdown > 10){
        alerts.push("⚠ Drawdown exceeded threshold");
    }

    if(alerts.length === 0){
        alerts = ["No alerts"];
    }

    document.getElementById("alerts").innerHTML =
        alerts.join("<br>");

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

}catch(e){

console.log("symbol load error",e)

}

applySymbolSelectFromBaseline()

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

console.log("WS MARKET DATA:", data)

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

}catch(e){

console.log(e)

}

}

function renderExecutionPipeline(){

const container = document.getElementById("execution_pipeline")

if(!container) return

container.innerHTML = `

<div class="pipeline">

<div id="p_signal" class="pipeline-step">Signal</div>
<div class="pipeline-arrow">→</div>

<div id="p_decision" class="pipeline-step">Decision</div>
<div class="pipeline-arrow">→</div>

<div id="p_risk" class="pipeline-step">Risk</div>
<div class="pipeline-arrow">→</div>

<div id="p_order" class="pipeline-step">Order</div>
<div class="pipeline-arrow">→</div>

<div id="p_exchange" class="pipeline-step">Exchange</div>
<div class="pipeline-arrow">→</div>

<div id="p_fill" class="pipeline-step">Fill</div>
<div class="pipeline-arrow">→</div>

<div id="p_position" class="pipeline-step">Position</div>

</div>

`

}

function updateExecutionPipeline(data){
const selectedStatus = sessionRuntimeStatus[selectedDashboardSession] || "UNKNOWN"
if(!dualPanelModeEnabled && selectedStatus !== "RUNNING"){
const steps = [
"signal",
"decision",
"risk",
"order",
"exchange",
"fill",
"position"
]
steps.forEach(s=>{
const el = document.getElementById("p_"+s)
if(!el) return
el.classList.remove("active","done")
})
return
}

let stage = "signal"

if(data.position?.side !== "flat"){

stage = "position"

}

else if(data.recent_trades && data.recent_trades.length>0){

stage = "fill"

}

const steps = [
"signal",
"decision",
"risk",
"order",
"exchange",
"fill",
"position"
]

steps.forEach(s=>{

const el = document.getElementById("p_"+s)

if(!el) return

el.classList.remove("active","done")

})

let done=true

steps.forEach(s=>{

const el = document.getElementById("p_"+s)

if(!el) return

if(done) el.classList.add("done")

if(s===stage){

el.classList.remove("done")

el.classList.add("active")

done=false

}

})

}

async function updateExecutionHistory(){

try{
const requestId = ++executionHistoryRequestId

const res = await fetch(`/api/execution/history?${getExecutionHistoryQueryParams()}`)

if(!res.ok) return

const data = await res.json()
if(requestId !== executionHistoryRequestId) return

const table = document.querySelector("#execution_history_table tbody")

if(!table) return

table.innerHTML=""

if(!data.history) return

const rows = data.history.slice(0,50)
rows.forEach(t => {

const time = new Date(t.time * 1000).toLocaleString()

const row = document.createElement("tr")

const sideColor =
t.side === "LONG"
? "#22c55e"
: t.side === "SHORT"
? "#ef4444"
: "#e2e8f0"

row.innerHTML=`

<td>${time}</td>
<td>${t.mode ?? "-"}</td>
<td>${t.symbol ?? "-"}</td>
<td>${t.strategy ?? "-"}</td>
<td style="color:${sideColor}">${t.side}</td>
<td>${t.size ?? "-"}</td>
<td>${t.fill_price ?? "-"}</td>
<td>${t.fee != null && t.fee !== "" ? t.fee : "-"}</td>
<td>${t.slippage ?? "-"}</td>
<td>${t.latency ?? "-"} ms</td>

`

table.appendChild(row)

})

}catch(e){

console.log("execution history error",e)

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

await fetch("/api/control/exchange",{
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

function updateMarketBias(data){

const bias = data?.market_bias

if(!bias){

document.getElementById("market_bias").innerHTML = `
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

document.getElementById("market_bias").innerHTML = `

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

const risk = document.getElementById("risk_input").value

try{

await fetch("/api/control/risk",{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({risk:parseFloat(risk)})
})

markControlApplyCommitted("risk_input", risk)

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

markControlApplyCommitted("trade_mode_select", mode)

flashButton(btn)

}catch(e){

console.error(e)

}

}


async function setTradingMode(btn){

const mode = document.getElementById("trading_mode_select").value

try{

await fetch("/api/control/mode",{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({mode})
})

markControlApplyCommitted("trading_mode_select", mode)

flashButton(btn)

}catch(e){

console.error(e)

}

}


async function setStrategy(btn){

const strategy = document.getElementById("strategy_select").value

try{

await fetch("/api/control/strategy",{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({strategy})
})

markControlApplyCommitted("strategy_select", strategy)

flashButton(btn)

}catch(e){

console.error(e)

}

}


async function setSymbol(btn){

const symbol = document.getElementById("symbol_select").value

try{

await fetch("/api/control/symbol",{
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