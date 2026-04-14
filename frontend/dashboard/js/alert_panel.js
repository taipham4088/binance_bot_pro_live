/**
 * Observability alert stream: GET /api/alerts + WS /ws/alerts
 * Targets #alert-list when present; non-blocking, max 200 rows in DOM.
 */
;(function () {
  var MAX_ROWS = 200

  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:"
    var port = location.port ? ":" + location.port : ""
    return proto + "//" + location.hostname + port + "/ws/alerts"
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
  }

  function levelClass(level) {
    var L = String(level || "").toUpperCase()
    if (L === "CRITICAL") return "ap-level-critical"
    if (L === "WARNING") return "ap-level-warning"
    return "ap-level-info"
  }

  function rowHtml(a) {
    var lvl = String(a.level || "INFO").toUpperCase()
    var msg = escapeHtml(String(a.message || ""))
    var src =
      a.source != null
        ? ' <span class="ap-src">' + escapeHtml(String(a.source)) + "</span>"
        : ""
    return (
      '<div class="ap-row ' +
      levelClass(lvl) +
      '"><span class="ap-lvl">[' +
      escapeHtml(lvl) +
      "]</span>" +
      src +
      '<span class="ap-msg">' +
      msg +
      "</span></div>"
    )
  }

  function renderList(el, items) {
    if (!el || !items || !items.length) {
      if (el) el.innerHTML = ""
      return
    }
    el.innerHTML = items.map(rowHtml).join("")
  }

  function prependAlert(el, a) {
    if (!el || !a) return
    var wrap = document.createElement("div")
    wrap.innerHTML = rowHtml(a).trim()
    var row = wrap.firstChild
    if (!row) return
    el.insertBefore(row, el.firstChild)
    while (el.children.length > MAX_ROWS) el.removeChild(el.lastChild)
  }

  function normalizePayload(data) {
    if (Array.isArray(data)) return data
    if (data && Array.isArray(data.alerts)) return data.alerts
    return []
  }

  document.addEventListener("DOMContentLoaded", function () {
    var list = document.getElementById("alert-list")
    if (!list) return
    list.setAttribute("data-managed", "alert-panel")

    fetch("/api/alerts")
      .then(function (r) {
        return r.ok ? r.json() : []
      })
      .then(function (data) {
        renderList(list, normalizePayload(data))
      })
      .catch(function () {})

    var ws
    function connect() {
      try {
        ws = new WebSocket(wsUrl())
      } catch (e) {
        return
      }
      ws.onmessage = function (ev) {
        try {
          var msg = JSON.parse(ev.data)
          if (msg.type === "snapshot" && Array.isArray(msg.alerts))
            renderList(list, msg.alerts)
          else if (msg.type === "alert" && msg.alert) prependAlert(list, msg.alert)
        } catch (e) {}
      }
      ws.onclose = function () {
        setTimeout(connect, 2000)
      }
      ws.onerror = function () {
        try {
          ws.close()
        } catch (e) {}
      }
    }
    connect()
  })
})()
