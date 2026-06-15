// BioMar Policy Library — static viewer. Reads library.json (produced by
// policy-formatter/tools/publish.py) and renders the catalogue. No backend.

const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];

function prettyDate(ym) {
  const [y, m] = (ym || "").split("-");
  return m ? `${MONTHS[parseInt(m, 10) - 1]} ${y}` : (ym || "—");
}

function latest(p) {
  return p.editions[p.editions.length - 1];
}

function card(p) {
  const ed = latest(p);
  const el = document.createElement("article");
  el.className = "card";
  const approvalRow = ed.approval_date
    ? `<br><b>Approved:</b> ${ed.approval_date}` : "";
  el.innerHTML = `
    <div>
      <h2 class="title">${p.title}</h2>
      <div class="tags">
        <span class="tag lang">${p.language || "English"}</span>
        <span class="tag">${ed.version || "Version 1"}</span>
        <span class="tag">${prettyDate(ed.date)}</span>
      </div>
      <div class="info">
        <b>Owner:</b> ${p.owner || "—"} &nbsp;·&nbsp; <b>Approver:</b> ${p.approver || "—"}
        ${approvalRow}
        <br><b>Last updated:</b> ${prettyDate(ed.date)} &nbsp;·&nbsp;
        <b>Editions:</b> ${p.editions.length}
      </div>
    </div>
    <div class="actions">
      <a class="btn primary" href="${ed.files.approval}" target="_blank" rel="noopener">
        Approval PDF <span class="arrow">↗</span></a>
      <a class="btn ghost" href="${ed.files.non_approval}" target="_blank" rel="noopener">
        Non-approval PDF <span class="arrow">↗</span></a>
    </div>`;
  return el;
}

let POLICIES = [];

function render(filter = "") {
  const list = document.getElementById("list");
  const f = filter.trim().toLowerCase();
  const shown = POLICIES.filter(p =>
    !f || p.title.toLowerCase().includes(f) ||
    (p.owner || "").toLowerCase().includes(f) ||
    (p.language || "").toLowerCase().includes(f));
  list.innerHTML = "";
  shown.forEach(p => list.appendChild(card(p)));
  document.getElementById("empty").hidden = shown.length > 0;
  document.getElementById("count").textContent =
    `${shown.length} of ${POLICIES.length} policies`;
}

async function init() {
  try {
    // Use embedded data when present (works from file:// with no server),
    // otherwise fetch library.json (served over HTTP / GitHub Pages).
    const data = window.LIBRARY ||
      await (await fetch("library.json", { cache: "no-store" })).json();
    POLICIES = (data.policies || []).slice()
      .sort((a, b) => a.title.localeCompare(b.title));
    document.getElementById("meta").textContent =
      `${POLICIES.length} policies · updated ${data.updated || ""}`;
    render();
    document.getElementById("search").addEventListener("input", e => render(e.target.value));
  } catch (err) {
    const e = document.getElementById("error");
    e.hidden = false;
    e.textContent = "Could not load library.json. Serve this folder over HTTP " +
      "(e.g. `python -m http.server` in docs/, or via GitHub Pages).";
  }
}

init();
