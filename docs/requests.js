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

const SR_ICON = { pass: "✓", fail: "✕", attention: "!", info: "·" };
const SR_BADGE = { pass: "AI self-check passed", fail: "AI self-check found issues", attention: "AI self-check — review" };

function selfReview(rep) {
  if (!rep || !rep.checks) return "";
  const cls = rep.overall === "pass" ? "sr-pass" : rep.overall === "fail" ? "sr-fail" : "sr-warn";
  const rows = rep.checks.map((c) =>
    `<li class="sr-${esc(c.status)}"><span class="sr-i">${SR_ICON[c.status] || "·"}</span>
       <span class="sr-l">${esc(c.label)}</span>${c.detail ? `<span class="sr-d">${esc(c.detail)}</span>` : ""}</li>`).join("");
  return `<div class="req-sr ${cls}">
    <div class="sr-head"><span class="sr-badge">${esc(SR_BADGE[rep.overall] || "AI self-check")}</span>
      <span class="sr-sum">${esc(rep.summary || "")}${rep.generated_at ? " · " + esc(rep.generated_at) : ""}</span></div>
    <ul class="sr-list">${rows}</ul></div>`;
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
  const sr = selfReview(r.self_review);
  return `<article class="req-card${r.kind === "new" ? " req-new" : ""}" data-status="${esc(r.current_status)}">
    ${r.kind === "new" ? '<div class="req-newbanner">✦ New policy requested</div>' : ""}
    <div class="req-head">
      <div>
        <span class="req-title">${esc(title)}</span>
        <span class="pending-badge ${s.cls}">${esc(s.label)}</span>
        ${varBadge}
      </div>
      <div class="req-when">${esc(fmtTime(r.created_at))}</div>
    </div>
    <div class="req-meta">Requested by <b>${esc(r.author || "—")}</b>${r.email ? ` · ${esc(r.email)}` : ""}${r.edition ? ` · ${esc(r.edition)}` : ""}${r.kind === "new" && r.versions ? ` · Versions: <b>${esc(r.versions)}</b>` : ""}${r.issue ? ` · issue #${esc(r.issue)}` : ""}</div>
    ${comment ? `<div class="req-comment"><div class="req-sec">Comment</div><p>${esc(comment)}</p></div>` : ""}
    ${hl}
    ${sr}
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

const PRIORITY = { new_policy: 0, change_pending: 1, pending_review: 2, done: 3 };

function render() {
  const list = document.getElementById("list");
  const shown = (FILTER ? REQUESTS.filter((r) => r.current_status === FILTER) : REQUESTS.slice())
    .sort((a, b) => (PRIORITY[a.current_status] ?? 9) - (PRIORITY[b.current_status] ?? 9) ||
      (a.created_at < b.created_at ? 1 : -1));
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
