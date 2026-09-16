// Shared "Ask the data" chat widget + results drawer -- injects its own
// markup and wires itself up. One definition, used on every page.
// Requires: chat-widget.css linked, Chart.js loaded, and optionally
// window.CHAT_CONFIG = { API_BASE_URL: "http://localhost:8000" } set
// before this script runs (defaults to localhost:8000 if omitted).

(function () {
  const CONFIG = Object.assign({ API_BASE_URL: "http://localhost:8000" }, window.CHAT_CONFIG || {});

  // ---- inject markup -----------------------------------------------------
  const launcher = document.createElement("button");
  launcher.id = "chatLauncher";
  launcher.title = "Ask the data";
  launcher.innerHTML = "<span>&#128172;</span>";
  document.body.appendChild(launcher);

  const chatPanel = document.createElement("div");
  chatPanel.id = "chatPanel";
  chatPanel.className = "chat-panel";
  chatPanel.hidden = true;
  chatPanel.innerHTML = `
    <div class="chat-head">
      <div>
        <strong>Ask the data</strong>
        <span class="sub">local templates + OpenRouter fallback</span>
      </div>
      <button class="icon-btn" id="chatClose" title="Close">&times;</button>
    </div>
    <div class="chat-messages" id="chatMessages">
      <div class="msg bot"><span class="badge">Assistant</span>Ask me things like "Which merchant has the highest chargeback count?" or "Show chargeback reason distribution."</div>
    </div>
    <form class="chat-form" id="chatForm">
      <input id="chatInput" type="text" placeholder="Ask a question about the data..." autocomplete="off" />
      <button type="submit" id="chatSend">Send</button>
    </form>
  `;
  document.body.appendChild(chatPanel);

  const resultsDrawer = document.createElement("div");
  resultsDrawer.id = "resultsDrawer";
  resultsDrawer.className = "results-drawer collapsed";
  resultsDrawer.hidden = true;
  resultsDrawer.innerHTML = `
    <div class="results-head">
      <span class="title" id="resultsTitle">Query Results</span>
      <div class="actions">
        <button class="icon-btn" id="resultsToggle" title="Expand/collapse">&#8636;</button>
        <button class="icon-btn" id="resultsClose" title="Close">&times;</button>
      </div>
    </div>
    <div class="results-body" id="resultsBody">
      <div class="results-empty">Ask a question in the chat to see results here.</div>
    </div>
  `;
  document.body.appendChild(resultsDrawer);

  // ---- agent health check --------------------------------------------
  async function checkAgentHealth() {
    const dot = document.getElementById("apiStatusDot");
    const text = document.getElementById("apiStatusText");
    if (!dot || !text) return;
    try {
      const res = await fetch(CONFIG.API_BASE_URL + "/health", { method: "GET" });
      if (!res.ok) throw new Error("bad status");
      const data = await res.json();
      dot.className = "status-dot ok";
      text.textContent = data.openrouter_fallback_configured
        ? `Agent online (OpenRouter: ${data.openrouter_model})`
        : "Agent online (local templates only)";
    } catch (e) {
      dot.className = "status-dot bad";
      text.textContent = "Agent offline";
    }
  }
  // nav-bar.js may inject the status-pill slightly after this runs; retry once.
  checkAgentHealth();
  setTimeout(checkAgentHealth, 300);
  setInterval(checkAgentHealth, 30000);

  // ---- chat panel open/close --------------------------------------------
  const chatClose = document.getElementById("chatClose");
  const chatMessages = document.getElementById("chatMessages");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const chatSend = document.getElementById("chatSend");

  launcher.addEventListener("click", () => {
    chatPanel.hidden = !chatPanel.hidden;
    if (!chatPanel.hidden) chatInput.focus();
  });
  chatClose.addEventListener("click", () => { chatPanel.hidden = true; });

  function addMessage(role, html, extraClass) {
    const div = document.createElement("div");
    div.className = "msg " + role + (extraClass ? " " + extraClass : "");
    div.innerHTML = html;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = chatInput.value.trim();
    if (!question) return;
    addMessage("user", escapeHtml(question));
    chatInput.value = "";
    chatInput.disabled = true;
    chatSend.disabled = true;
    const thinkingMsg = addMessage("bot", "Thinking...", "thinking");

    try {
      const res = await fetch(CONFIG.API_BASE_URL + "/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      thinkingMsg.remove();

      if (!res.ok) {
        addMessage("bot", escapeHtml(data.detail || "The agent returned an error."), "error");
        return;
      }

      const ctx = data.llm_context_extraction || {};
      const badge = ctx.source === "openrouter" ? `OpenRouter (${ctx.model})` : "Local template";
      const summary = (data.collapsible_suggested_answer || {}).answer_summary || "No answer summary returned.";
      addMessage("bot", `<span class="badge">${escapeHtml(badge)}</span>${escapeHtml(summary)}`);

      renderResults(question, data);
    } catch (err) {
      thinkingMsg.remove();
      addMessage("bot", "Couldn't reach the agent. Is the FastAPI backend running at " + escapeHtml(CONFIG.API_BASE_URL) + "?", "error");
    } finally {
      chatInput.disabled = false;
      chatSend.disabled = false;
      chatInput.focus();
    }
  });

  // ---- results drawer -----------------------------------------------
  const resultsBody = document.getElementById("resultsBody");
  const resultsTitle = document.getElementById("resultsTitle");
  const resultsToggle = document.getElementById("resultsToggle");
  const resultsClose = document.getElementById("resultsClose");
  let currentChart = null;
  let currentChartLabel = "chart";

  resultsToggle.addEventListener("click", () => {
    resultsDrawer.classList.toggle("collapsed");
  });
  resultsClose.addEventListener("click", () => {
    resultsDrawer.hidden = true;
  });

  function slugify(s) {
    return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 60) || "chart";
  }

  function downloadChartImage() {
    if (!currentChart) return;
    const url = currentChart.toBase64Image("image/png", 1);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentChartLabel}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function shareChartImage() {
    if (!currentChart) return;
    const dataUrl = currentChart.toBase64Image("image/png", 1);
    try {
      const blob = await (await fetch(dataUrl)).blob();
      const file = new File([blob], `${currentChartLabel}.png`, { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: currentChartLabel });
        return;
      }
    } catch (e) { /* fall through to download */ }
    downloadChartImage();
  }

  function renderResults(question, data) {
    const viz = data.visualization || {};
    const rows = data.rows || [];
    const er = data.er_relationship_mapping || {};
    const followups = data.index_space_followups || [];

    resultsDrawer.hidden = false;
    resultsDrawer.classList.remove("collapsed");
    resultsTitle.textContent = viz.title || question;
    currentChartLabel = slugify(viz.title || question);

    resultsBody.innerHTML = "";

    const summaryEl = document.createElement("div");
    summaryEl.className = "result-summary";
    summaryEl.innerHTML = `<strong>${escapeHtml(question)}</strong>`;
    resultsBody.appendChild(summaryEl);

    if (currentChart) { currentChart.destroy(); currentChart = null; }

    if (viz.type === "metric_card" && rows.length) {
      const row = rows[0];
      const keys = Object.keys(row);
      const valueKey = viz.y_axis && row[viz.y_axis] !== undefined ? viz.y_axis : keys[keys.length - 1];
      const card = document.createElement("div");
      card.className = "metric-card";
      card.innerHTML = `<div class="value">${escapeHtml(formatValue(row[valueKey]))}</div><div class="label">${escapeHtml(viz.title || valueKey)}</div>`;
      resultsBody.appendChild(card);
    } else if (rows.length && viz.x_axis && viz.y_axis) {
      const wrap = document.createElement("div");
      wrap.className = "chart-wrap";
      const canvas = document.createElement("canvas");
      wrap.appendChild(canvas);
      resultsBody.appendChild(wrap);

      const actions = document.createElement("div");
      actions.className = "chart-actions";
      actions.innerHTML = `
        <button type="button" id="dlChartBtn">&#8681; Download PNG</button>
        <button type="button" id="shareChartBtn">&#8599; Share image</button>
      `;
      resultsBody.appendChild(actions);
      actions.querySelector("#dlChartBtn").addEventListener("click", downloadChartImage);
      actions.querySelector("#shareChartBtn").addEventListener("click", shareChartImage);

      const labels = rows.map((r) => r[viz.x_axis]);
      const values = rows.map((r) => Number(r[viz.y_axis]) || 0);
      const chartType = (viz.type === "donut" || viz.type === "pie") ? "doughnut" : (viz.type === "line" ? "line" : "bar");

      currentChart = new Chart(canvas.getContext("2d"), {
        type: chartType,
        data: {
          labels,
          datasets: [{
            label: viz.y_axis,
            data: values,
            backgroundColor: ["#6366F1", "#06B6D4", "#059669", "#D97706", "#DC2626", "#8B5CF6", "#EC4899", "#14B8A6"],
            borderColor: "#6366F1",
            borderWidth: chartType === "line" ? 2 : 0,
            tension: 0.3,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          backgroundColor: "#FFFFFF",
          plugins: { legend: { display: chartType === "doughnut", labels: { color: "#475569" } } },
          scales: chartType === "doughnut" ? {} : {
            x: { ticks: { color: "#94A3B8", maxRotation: 40, minRotation: 0 }, grid: { color: "rgba(15,23,42,0.06)" } },
            y: { ticks: { color: "#94A3B8" }, grid: { color: "rgba(15,23,42,0.06)" } },
          },
        },
        plugins: [{
          id: "whiteBackground",
          beforeDraw: (chart) => {
            const ctx = chart.canvas.getContext("2d");
            ctx.save();
            ctx.globalCompositeOperation = "destination-over";
            ctx.fillStyle = "#FFFFFF";
            ctx.fillRect(0, 0, chart.width, chart.height);
            ctx.restore();
          },
        }],
      });
    } else if (rows.length) {
      resultsBody.appendChild(buildTable(rows));
    } else {
      const empty = document.createElement("div");
      empty.className = "results-empty";
      empty.textContent = "No rows returned.";
      resultsBody.appendChild(empty);
    }

    if (data.sql_query) {
      const details = document.createElement("details");
      details.className = "sql-details";
      details.innerHTML = `
        <summary>SQL &amp; data lineage</summary>
        <pre>${escapeHtml(data.sql_query)}</pre>
        ${er.primary_table ? `<div class="er-line">Primary table: ${escapeHtml(er.primary_table)}</div>` : ""}
        ${er.joined_tables && er.joined_tables.length ? `<div class="er-line">Joined: ${escapeHtml(er.joined_tables.join(", "))}</div>` : ""}
        ${er.kpis_calculated && er.kpis_calculated.length ? `<div class="er-line">KPIs: ${escapeHtml(er.kpis_calculated.join(", "))}</div>` : ""}
      `;
      resultsBody.appendChild(details);
    }

    if (followups.length) {
      const wrap = document.createElement("div");
      wrap.className = "followups";
      followups.forEach((f) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "followup-chip";
        chip.textContent = f;
        chip.addEventListener("click", () => {
          chatPanel.hidden = false;
          chatInput.value = f;
          chatForm.dispatchEvent(new Event("submit"));
        });
        wrap.appendChild(chip);
      });
      resultsBody.appendChild(wrap);
    }
  }

  function buildTable(rows) {
    const cols = Object.keys(rows[0]);
    const table = document.createElement("table");
    table.style.width = "100%";
    table.style.fontSize = "11.5px";
    table.style.borderCollapse = "collapse";
    const thead = document.createElement("thead");
    thead.innerHTML = "<tr>" + cols.map((c) => `<th style="text-align:left;padding:6px;border-bottom:1px solid var(--border);color:var(--text-secondary);">${escapeHtml(c)}</th>`).join("") + "</tr>";
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    rows.slice(0, 50).forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML = cols.map((c) => `<td style="padding:6px;border-bottom:1px solid var(--border);">${escapeHtml(formatValue(r[c]))}</td>`).join("");
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    const wrap = document.createElement("div");
    wrap.style.overflowX = "auto";
    wrap.style.marginBottom = "14px";
    wrap.appendChild(table);
    return wrap;
  }

  function formatValue(v) {
    if (typeof v === "number") {
      return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    return v === null || v === undefined ? "--" : v;
  }
})();
