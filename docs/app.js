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

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function card(p) {
  const ed = latest(p);
  const el = document.createElement("article");
  el.className = "card";
  const approvalRow = ed.approval_date
    ? `<br><b>Approved:</b> ${esc(ed.approval_date)}` : "";
  const n = p.editions.length;
  el.innerHTML = `
    <div>
      <h2 class="title">${esc(p.title)}</h2>
      <div class="tags">
        <span class="tag lang">${esc(p.language || "English")}</span>
        <span class="tag">${esc(ed.version || "Version 1")}</span>
        <span class="tag">${prettyDate(ed.date)}</span>
      </div>
      <div class="info">
        <b>Owner:</b> ${esc(p.owner || "—")} &nbsp;·&nbsp; <b>Approver:</b> ${esc(p.approver || "—")}
        ${approvalRow}
        <br><b>Last updated:</b> ${prettyDate(ed.date)} &nbsp;·&nbsp;
        <b>Editions:</b> ${n}
      </div>
    </div>
    <div class="actions">
      <a class="btn primary" href="${esc(ed.files.approval)}" target="_blank" rel="noopener">
        Approval PDF <span class="arrow">↗</span></a>
      <a class="btn ghost" href="${esc(ed.files.non_approval)}" target="_blank" rel="noopener">
        Non-approval PDF <span class="arrow">↗</span></a>
      <button type="button" class="btn history">
        Version history <span class="badge">${n}</span></button>
    </div>`;
  el.querySelector(".history").addEventListener("click", () => openHistory(p));
  return el;
}

// ---- Version history modal -----------------------------------------------

function editionRow(ed, isLatest) {
  const appr = ed.approval_date
    ? `<span><b>Approved:</b> ${esc(ed.approval_date)}</span>` : "";
  const gen = ed.generated_at
    ? `<span><b>Generated:</b> ${esc(ed.generated_at)}</span>` : "";
  const notes = ed.notes
    ? `<p class="vh-notes">${esc(ed.notes)}</p>` : "";
  return `
    <li class="vh-item${isLatest ? " current" : ""}">
      <div class="vh-head">
        <span class="vh-version">${esc(ed.version || "Version 1")}</span>
        <span class="tag">${prettyDate(ed.date)}</span>
        ${isLatest ? '<span class="vh-current">Current</span>' : ""}
      </div>
      <div class="vh-meta">${appr}${gen}</div>
      ${notes}
      <div class="vh-files">
        <a href="${esc(ed.files.approval)}" target="_blank" rel="noopener">Approval PDF ↗</a>
        <a href="${esc(ed.files.non_approval)}" target="_blank" rel="noopener">Non-approval PDF ↗</a>
      </div>
    </li>`;
}

function openHistory(p) {
  const dlg = document.getElementById("history");
  const last = p.editions.length - 1;
  dlg.querySelector(".vh-title").textContent = `${p.title} — version history`;
  dlg.querySelector(".vh-sub").textContent =
    `${p.editions.length} edition${p.editions.length !== 1 ? "s" : ""} · Owner: ${p.owner || "—"}`;
  dlg.querySelector(".vh-list").innerHTML =
    p.editions.map((ed, i) => editionRow(ed, i === last)).reverse().join("");
  if (typeof dlg.showModal === "function") dlg.showModal();
  else dlg.setAttribute("open", "");
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
      `${POLICIES.length} policies · Last update: ${data.updated || ""}`;
    render();
    document.getElementById("search").addEventListener("input", e => render(e.target.value));
    const connectBtn = document.getElementById("connectBtn");
    const connectDlg = document.getElementById("connect");
    if (connectBtn && connectDlg) {
      connectBtn.addEventListener("click", () => {
        if (typeof connectDlg.showModal === "function") connectDlg.showModal();
        else connectDlg.setAttribute("open", "");
      });
    }
  } catch (err) {
    const e = document.getElementById("error");
    e.hidden = false;
    e.textContent = "Could not load library.json. Serve this folder over HTTP " +
      "(e.g. `python -m http.server` in docs/, or via GitHub Pages).";
  }
}

init();
