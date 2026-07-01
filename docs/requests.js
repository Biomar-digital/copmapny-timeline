"use strict";

const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function fmtTime(iso) {
  const d = new Date(iso);
  return isNaN(d) ? esc(iso) : d.toLocaleString(undefined,
    { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const STATUS = {
  change_pending: { label: "Change pending", cls: "change" },
  pending_review: { label: "Pending for review", cls: "review" },
  done: { label: "Done", cls: "done" },
  new_policy: { label: "New policy", cls: "newp" },
};

let REQUESTS = [];
let POLICIES = [];
let COMMENTS = {};        // policy id -> comments[]
let FILTER = null;

function policyById(id) { return POLICIES.find((p) => p.id === id); }

function latest(p) { return p.editions[p.editions.length - 1]; }
function edKey(ed) { return `${ed.version || "Version 1"}__${ed.date}`; }

// The file the requester marked up, so "view highlighted document" opens it.
function annotatedFile(p, variant) {
  const d = (latest(p).documents || [])[0];
  if (!d || !d.files) return null;
  if (variant === "Signed" && d.files.approval) return d.files.approval;
  return d.files.non_approval || d.files.approval || null;
}

function reviewHref(r) {
  const p = policyById(r.policy);
  if (!p) return null;
  const file = annotatedFile(p, r.variant);
  if (!file) return null;
  const q = new URLSearchParams({
    policy: r.policy, file, edition: r.edition || edKey(latest(p)),
    title: p.title, view: "1",
  });
  if (r.variant) q.set("variant", r.variant);
  return "review.html?" + q.toString();
}

async function loadComments(policyId) {
  if (COMMENTS[policyId]) return COMMENTS[policyId];
  try {
    const r = await fetch(`api/comments?policy=${encodeURIComponent(policyId)}`, { cache: "no-store" });
    const d = await r.json();
    COMMENTS[policyId] = d.comments || [];
  } catch { COMMENTS[policyId] = []; }
  return COMMENTS[policyId];
}

function detailBlocks(details) {
  // The request text folds the comment and a "Highlights:" list together.
  const idx = details.indexOf("Highlights:");
  if (idx === -1) return { comment: details.trim(), highlights: [] };
  const comment = details.slice(0, idx).trim();
  const highlights = details.slice(idx + "Highlights:".length)
    .split("\n").map((l) => l.replace(/^•\s*/, "").trim()).filter(Boolean);
  return { comment, highlights };
}

function requestCard(r) {
  const p = policyById(r.policy);
  const s = STATUS[r.current_status] || { label: r.current_status || "—", cls: "change" };
  const title = p ? p.title : (r.title || r.policy || "—");
  const { comment, highlights } = detailBlocks(r.details || "");
  const rev = reviewHref(r);
  const varBadge = r.variant
    ? `<span class="req-variant">${esc(r.variant)}${r.variant === "Both" ? " (signed + unsigned)" : ""}</span>` : "";
  const fileRow = r.upload
    ? `<a class="btn word" href="api/admin/requests/file?path=${encodeURIComponent(r.upload)}">⬇ ${esc(r.upload.split("/").pop())}</a>` : "";
  const hl = highlights.length
    ? `<div class="req-hl"><div class="req-sec">Highlights on the document (${highlights.length})</div>
        <ul>${highlights.map((h) => `<li>${esc(h)}</li>`).join("")}</ul></div>` : "";
  return `<article class="req-card" data-status="${esc(r.current_status)}">
    <div class="req-head">
      <div>
        <span class="req-title">${esc(title)}</span>
        <span class="pending-badge ${s.cls}">${esc(s.label)}</span>
        ${varBadge}
        ${r.kind === "new" ? '<span class="req-kind">New policy</span>' : ""}
      </div>
      <div class="req-when">${esc(fmtTime(r.created_at))}</div>
    </div>
    <div class="req-meta">Requested by <b>${esc(r.author || "—")}</b>${r.email ? ` · ${esc(r.email)}` : ""}${r.edition ? ` · ${esc(r.edition)}` : ""}${r.issue ? ` · issue #${esc(r.issue)}` : ""}</div>
    ${comment ? `<div class="req-comment"><div class="req-sec">Comment</div><p>${esc(comment)}</p></div>` : ""}
    ${hl}
    <div class="req-cmt" data-policy="${esc(r.policy)}" data-edition="${esc(r.edition || "")}"></div>
    <div class="req-actions">
      ${rev ? `<a class="btn primary" href="${esc(rev)}">🔍 View highlighted document</a>` : ""}
      ${fileRow}
    </div>
  </article>`;
}

async function fillComments() {
  for (const el of document.querySelectorAll(".req-cmt")) {
    const pid = el.dataset.policy, ed = el.dataset.edition;
    if (!pid) continue;
    const all = await loadComments(pid);
    const mine = all.filter((c) => !ed || c.edition === ed);
    if (!mine.length) continue;
    el.innerHTML = `<div class="req-sec">Comments on this version (${mine.length})</div>` +
      mine.map((c) => `<div class="req-cbubble"><b>${esc(c.author || "Anonymous")}</b>
        <span class="req-ctime">${esc(fmtTime(c.created_at))}</span><p>${esc(c.text)}</p></div>`).join("");
  }
}

function render() {
  const list = document.getElementById("list");
  const shown = FILTER ? REQUESTS.filter((r) => r.current_status === FILTER) : REQUESTS;
  document.getElementById("empty").hidden = shown.length > 0;
  list.innerHTML = shown.map(requestCard).join("");
  document.getElementById("meta").textContent =
    `${REQUESTS.length} request${REQUESTS.length !== 1 ? "s" : ""} in total.`;
  fillComments();
}

function renderFilter() {
  const el = document.getElementById("statusfilter");
  const count = (s) => REQUESTS.filter((r) => r.current_status === s).length;
  const defs = [["change_pending", "Change pending"], ["pending_review", "Pending for review"],
    ["done", "Done"], ["new_policy", "New policy"]];
  const isActive = (v) => v === "__all" ? FILTER === null : FILTER === v;
  const btn = (v, l, n) =>
    `<button type="button" class="sfilter sf-${esc(v)}${isActive(v) ? " active" : ""}" data-val="${esc(v)}">${esc(l)} <span class="sf-count">${n}</span></button>`;
  el.innerHTML = '<span class="chips-label">Status</span>' +
    btn("__all", "All", REQUESTS.length) +
    defs.filter(([v]) => count(v)).map(([v, l]) => btn(v, l, count(v))).join("");
  el.querySelectorAll(".sfilter").forEach((b) => b.addEventListener("click", () => {
    const v = b.dataset.val;
    FILTER = (v === "__all" || FILTER === v) ? null : v;
    renderFilter(); render();
  }));
}

async function init() {
  let me = null;
  try { me = (await (await fetch("api/auth/me", { cache: "no-store" })).json()).user; } catch {}
  if (!me) { location.href = "login"; return; }
  if (me.role !== "admin") {
    document.getElementById("error").hidden = false;
    document.getElementById("error").textContent = "This page is for administrators only.";
    return;
  }
  POLICIES = (window.LIBRARY && window.LIBRARY.policies) ||
    ((await (await fetch("library.json", { cache: "no-store" })).json()).policies) || [];
  try {
    const d = await (await fetch("api/admin/requests", { cache: "no-store" })).json();
    REQUESTS = d.requests || [];
  } catch (e) {
    document.getElementById("error").hidden = false;
    document.getElementById("error").textContent = "Could not load requests: " + e.message;
    return;
  }
  renderFilter();
  render();
}

init();
