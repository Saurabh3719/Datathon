// Shared top navigation bar -- single source of truth for every page.
// Usage: <nav class="top-nav" id="siteNav" data-active="dashboard"></nav>
// then <script src="nav-bar.js"></script> anywhere after it in the DOM.
// data-active is one of: dashboard | workflow | team | information

(function () {
  const ICONS = {
    dashboard: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="12" width="4" height="9"/><rect x="10" y="7" width="4" height="14"/><rect x="17" y="3" width="4" height="18"/></svg>',
    workflow: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="6" r="2.5"/><circle cx="19" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M7 7.5 L10.5 16 M17 7.5 L13.5 16"/></svg>',
    team: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17.5" cy="9" r="2.6"/><path d="M15.5 14.2c2.9.4 5 2.7 5 5.8"/></svg>',
    information: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><line x1="12" y1="11" x2="12" y2="16.5"/><circle cx="12" cy="7.6" r="0.9" fill="currentColor" stroke="none"/></svg>',
  };

  const GITHUB_SVG = '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>';

  const PAGES = [
    { key: "dashboard", href: "index.html", label: "Dashboard" },
    { key: "workflow", href: "workflow.html", label: "Workflow" },
    { key: "team", href: "team.html", label: "Team" },
    { key: "information", href: "information.html", label: "Information" },
  ];

  function mount(nav) {
    const active = nav.dataset.active || "";
    const links = PAGES.map((p) => `
      <a href="${p.href}" class="${p.key === active ? "active" : ""}">
        ${ICONS[p.key]}<span class="label">${p.label}</span>
      </a>
    `).join("");

    nav.innerHTML = `
      <div class="brand">
        <div class="logo-dot">U</div>
        <div>
          <strong>TR-1: Analytics of TransOrg</strong>
          <span class="sub">UPI Fraud &amp; Merchant Risk Analytics</span>
        </div>
      </div>
      <div class="nav-links">
        ${links}
        <a href="https://github.com/Manudevchhiller/Datathon" class="gh-link" target="_blank" rel="noopener">
          ${GITHUB_SVG}<span class="label">GitHub</span>
        </a>
      </div>
      <span class="status-pill"><span id="apiStatusDot" class="status-dot"></span><span id="apiStatusText">Checking agent...</span></span>
    `;
  }

  document.querySelectorAll("nav.top-nav[id]").forEach(mount);
})();
