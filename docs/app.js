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

const PDF_LABELS = {
  approval: {
    label: "Signed PDF",
    tip: "Official approved version — includes the Board of Directors signature/approval page and the version card.",
  },
  non_approval: {
    label: "Unsigned PDF",
    tip: "The policy text only — without the signature/approval page.",
  },
};

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
      <a class="btn primary" href="${esc(ed.files.approval)}" target="_blank" rel="noopener" title="${esc(PDF_LABELS.approval.tip)}">
        ${PDF_LABELS.approval.label} <span class="arrow">↗</span></a>
      <a class="btn ghost" href="${esc(ed.files.non_approval)}" target="_blank" rel="noopener" title="${esc(PDF_LABELS.non_approval.tip)}">
        ${PDF_LABELS.non_approval.label} <span class="arrow">↗</span></a>
      <button type="button" class="btn history">
        Version history <span class="badge">${n}</span></button>
    </div>`;
  el.querySelector(".history").addEventListener("click", () => openHistory(p));
  return el;
}

// ---- Version history modal -----------------------------------------------

function savedAuthor() {
  try { return localStorage.getItem("biomar-author") || ""; } catch { return ""; }
}

function edKey(ed) {
  return `${ed.version || "Version 1"}__${ed.date}`;
}

function annHref(p, ed, file) {
  const q = new URLSearchParams({ policy: p.id, edition: edKey(ed), title: p.title, file });
  return "review.html?" + q.toString();
}

function fmtTime(iso) {
  const d = new Date(iso);
  return isNaN(d) ? esc(iso) : d.toLocaleString(undefined,
    { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function editionRow(p, ed, isLatest) {
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
        <a href="${esc(ed.files.approval)}" target="_blank" rel="noopener" title="${esc(PDF_LABELS.approval.tip)}">${PDF_LABELS.approval.label} ↗</a>
        <a class="vh-annotate" href="${esc(annHref(p, ed, ed.files.approval))}">✎ Annotate</a>
        <a href="${esc(ed.files.non_approval)}" target="_blank" rel="noopener" title="${esc(PDF_LABELS.non_approval.tip)}">${PDF_LABELS.non_approval.label} ↗</a>
        <a class="vh-annotate" href="${esc(annHref(p, ed, ed.files.non_approval))}">✎ Annotate</a>
      </div>
      <div class="vh-comments" data-key="${esc(edKey(ed))}">
        <div class="vh-clabel">Comments</div>
        <div class="vh-clist"><p class="vh-cempty">Loading…</p></div>
        <div class="vh-cform">
          <textarea class="vh-ctext" rows="2" placeholder="Add a comment for the team / AI…"></textarea>
          <div class="vh-crow">
            <button type="button" class="btn vh-cadd">Add comment</button>
            <span class="vh-cstatus"></span>
          </div>
        </div>
      </div>
    </li>`;
}

// ---- comments API ----

async function apiGetComments(policyId) {
  const r = await fetch(`api/comments?policy=${encodeURIComponent(policyId)}`, { cache: "no-store" });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d.comments || [];
}

async function apiPostComment(policyId, edition, author, text) {
  const r = await fetch("api/comments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy: policyId, edition, author, text }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d.comment;
}

function renderCommentList(el, comments) {
  if (!comments.length) {
    el.innerHTML = '<p class="vh-cempty">No comments yet.</p>';
    return;
  }
  el.innerHTML = comments.map(c => `
    <div class="vh-comment">
      <div class="vh-cmeta"><b>${esc(c.author || "Anonymous")}</b> · ${fmtTime(c.created_at)}</div>
      <p>${esc(c.text)}</p>
    </div>`).join("");
}

async function loadComments(policyId) {
  const dlg = document.getElementById("history");
  const conts = [...dlg.querySelectorAll(".vh-comments")];
  let byEd = {};
  let err = null;
  try {
    for (const c of await apiGetComments(policyId)) {
      (byEd[c.edition] = byEd[c.edition] || []).push(c);
    }
  } catch (e) { err = e; }
  conts.forEach(cont => {
    const list = cont.querySelector(".vh-clist");
    if (err) list.innerHTML = `<p class="vh-cempty">Comments unavailable (${esc(err.message)}).</p>`;
    else renderCommentList(list, byEd[cont.dataset.key] || []);
  });
}

function wireComments(policyId) {
  const dlg = document.getElementById("history");
  dlg.querySelectorAll(".vh-comments").forEach(cont => {
    const btn = cont.querySelector(".vh-cadd");
    btn.addEventListener("click", async () => {
      const textEl = cont.querySelector(".vh-ctext");
      const status = cont.querySelector(".vh-cstatus");
      const text = textEl.value.trim();
      if (!text) { status.textContent = "Write a comment first."; return; }
      btn.disabled = true; status.textContent = "Saving…";
      try {
        await apiPostComment(policyId, cont.dataset.key, "", text);
        textEl.value = "";
        status.textContent = "Saved ✓";
        const all = await apiGetComments(policyId);
        renderCommentList(cont.querySelector(".vh-clist"),
          all.filter(c => c.edition === cont.dataset.key));
      } catch (e) {
        status.textContent = "Could not save: " + e.message;
      } finally { btn.disabled = false; }
    });
  });
}

// ---- requests (change / new policy, with optional upload) ----

let HISTORY_POLICY = null;

function openRequest(mode, policy) {
  const dlg = document.getElementById("request");
  const isNew = mode === "new";
  document.getElementById("reqTitle").textContent =
    isNew ? "Request a new policy" : "Request a change";
  document.getElementById("reqSub").textContent = isNew
    ? "Describe the policy you need and optionally attach a draft."
    : `Policy: ${policy ? policy.title : "—"}`;
  document.getElementById("reqTitleField").style.display = isNew ? "" : "none";
  document.getElementById("reqDetailsLabel").textContent =
    isNew ? "What should this policy cover? *" : "What change do you need? *";
  document.getElementById("reqDocTitle").value = "";
  document.getElementById("reqDetails").value = "";
  document.getElementById("reqFile").value = "";
  document.getElementById("reqStatus").textContent = "";
  dlg.dataset.mode = mode;
  dlg.dataset.policy = isNew ? "" : (policy ? policy.id : "");
  dlg.dataset.title = isNew ? "" : (policy ? policy.title : "");
  if (typeof dlg.showModal === "function") dlg.showModal();
  else dlg.setAttribute("open", "");
}

async function submitRequest() {
  const dlg = document.getElementById("request");
  const mode = dlg.dataset.mode || "new";
  const status = document.getElementById("reqStatus");
  const details = document.getElementById("reqDetails").value.trim();
  const docTitle = document.getElementById("reqDocTitle").value.trim();
  const fileEl = document.getElementById("reqFile");
  if (!details) { status.textContent = "Please describe your request."; return; }
  if (mode === "new" && !docTitle) { status.textContent = "Enter a title for the new policy."; return; }

  const fd = new FormData();
  fd.set("kind", mode === "new" ? "new" : "change");
  fd.set("details", details);
  if (mode === "new") fd.set("title", docTitle);
  else { fd.set("policy", dlg.dataset.policy || ""); fd.set("title", dlg.dataset.title || ""); }
  if (fileEl.files && fileEl.files[0]) fd.set("file", fileEl.files[0]);

  const btn = document.getElementById("reqSubmit");
  btn.disabled = true; status.textContent = "Sending…";
  try {
    const r = await fetch("api/requests", { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    status.textContent = "Request sent ✓ — thank you!";
    setTimeout(() => dlg.close && dlg.close(), 1200);
  } catch (e) {
    status.textContent = "Could not send: " + e.message;
  } finally {
    btn.disabled = false;
  }
}

function openHistory(p) {
  HISTORY_POLICY = p;
  const dlg = document.getElementById("history");
  const last = p.editions.length - 1;
  dlg.querySelector(".vh-title").textContent = `${p.title} — version history`;
  dlg.querySelector(".vh-sub").textContent =
    `${p.editions.length} edition${p.editions.length !== 1 ? "s" : ""} · Owner: ${p.owner || "—"}`;
  dlg.querySelector(".vh-list").innerHTML =
    p.editions.map((ed, i) => editionRow(p, ed, i === last)).reverse().join("");
  if (typeof dlg.showModal === "function") dlg.showModal();
  else dlg.setAttribute("open", "");
  wireComments(p.id);
  loadComments(p.id);
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

// ---- account + admin (bell / approvals) ----

const EVENT_LABEL = {
  account_request: "Account request", account_approved: "Account approved",
  account_rejected: "Account rejected", comment: "New comment", annotation: "New annotation",
  request_new: "New policy request", request_change: "Change request",
};

async function setupAccount() {
  let me = null;
  try { me = (await (await fetch("api/auth/me", { cache: "no-store" })).json()).user; } catch {}
  if (!me) return;
  document.getElementById("acctName").textContent = me.name;
  const logout = document.getElementById("logoutBtn");
  logout.hidden = false;
  logout.addEventListener("click", async () => {
    try { await fetch("api/auth/logout", { method: "POST" }); } catch {}
    location.href = "/login";
  });
  if (me.role === "admin") setupAdmin();
}

async function setupAdmin() {
  const bell = document.getElementById("bellBtn");
  bell.hidden = false;
  bell.addEventListener("click", openAdmin);
  document.getElementById("adminClose").addEventListener("click",
    () => { const d = document.getElementById("admin"); if (d.close) d.close(); });
  document.querySelectorAll(".ad-tab").forEach(t => t.addEventListener("click", () => {
    document.querySelectorAll(".ad-tab").forEach(x => x.classList.toggle("active", x === t));
    document.getElementById("adNotifs").hidden = t.dataset.tab !== "notifs";
    document.getElementById("adPending").hidden = t.dataset.tab !== "pending";
  }));
  await refreshBadges();
}

async function refreshBadges() {
  try {
    const d = await (await fetch("api/admin/inbox", { cache: "no-store" })).json();
    const b = document.getElementById("bellBadge");
    if (d.unread > 0) { b.hidden = false; b.textContent = d.unread > 99 ? "99+" : d.unread; } else b.hidden = true;
  } catch {}
  try {
    const d = await (await fetch("api/admin/users?status=pending", { cache: "no-store" })).json();
    const n = (d.users || []).length;
    const pb = document.getElementById("pendBadge");
    if (n > 0) { pb.hidden = false; pb.textContent = n; } else pb.hidden = true;
  } catch {}
}

async function openAdmin() {
  const dlg = document.getElementById("admin");
  if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
  const notifs = document.getElementById("adNotifs");
  notifs.innerHTML = '<p class="ad-empty">Loading…</p>';
  try {
    const d = await (await fetch("api/admin/inbox", { cache: "no-store" })).json();
    notifs.innerHTML = (d.events || []).length ? d.events.map(e => `
      <div class="ad-item">
        <div class="ad-h"><b>${esc(EVENT_LABEL[e.type] || e.type)}</b> · ${fmtTime(new Date(e.created_at).toISOString())}</div>
        <div class="ad-s">${esc(e.summary || "")}</div>
      </div>`).join("") : '<p class="ad-empty">No notifications yet.</p>';
  } catch (e) { notifs.innerHTML = `<p class="ad-empty">Could not load (${esc(e.message)}).</p>`; }
  try { await fetch("api/admin/inbox/seen", { method: "POST" }); } catch {}
  document.getElementById("bellBadge").hidden = true;
  await loadPending();
}

async function loadPending() {
  const el = document.getElementById("adPending");
  el.innerHTML = '<p class="ad-empty">Loading…</p>';
  try {
    const d = await (await fetch("api/admin/users?status=pending", { cache: "no-store" })).json();
    const users = d.users || [];
    if (!users.length) { el.innerHTML = '<p class="ad-empty">No pending accounts.</p>'; return; }
    el.innerHTML = users.map(u => `
      <div class="ad-item" data-id="${esc(u.id)}">
        <div class="ad-h"><b>${esc(u.name)}</b> · ${esc(u.email)}</div>
        <div class="ad-actions">
          <button type="button" class="btn vh-cadd ad-approve">Approve</button>
          <button type="button" class="btn ghost ad-reject">Reject</button>
        </div>
      </div>`).join("");
    el.querySelectorAll(".ad-item").forEach(item => {
      const id = item.dataset.id;
      item.querySelector(".ad-approve").addEventListener("click", () => decideUser(id, "approve", item));
      item.querySelector(".ad-reject").addEventListener("click", () => decideUser(id, "reject", item));
    });
  } catch (e) { el.innerHTML = `<p class="ad-empty">Could not load (${esc(e.message)}).</p>`; }
}

async function decideUser(id, action, item) {
  try {
    const r = await fetch(`api/admin/users/${action}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }),
    });
    if (!r.ok) throw new Error("HTTP " + r.status);
    item.remove();
    await refreshBadges();
  } catch (e) { alert("Could not update: " + e.message); }
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
    document.getElementById("newReqBtn").addEventListener("click", () => openRequest("new"));
    document.getElementById("reqChangeBtn").addEventListener("click", () => {
      const dlg = document.getElementById("history");
      if (dlg.close) dlg.close();
      openRequest("change", HISTORY_POLICY);
    });
    document.getElementById("reqClose").addEventListener("click",
      () => { const d = document.getElementById("request"); if (d.close) d.close(); });
    document.getElementById("reqSubmit").addEventListener("click", submitRequest);
    setupAccount();
  } catch (err) {
    const e = document.getElementById("error");
    e.hidden = false;
    e.textContent = "Could not load library.json. Serve this folder over HTTP " +
      "(e.g. `python -m http.server` in docs/, or via GitHub Pages).";
  }
}

init();
