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

function wordLink(doc) {
  if (!doc.files || !doc.files.word) return "";
  return `
      <a class="btn word" href="${esc(doc.files.word)}" download title="Editable Word (.docx) copy — same content and branding as the PDF">
        Word <span class="arrow">↓</span></a>`;
}

function docLinks(doc, multi) {
  const pfx = multi ? esc(doc.label) + " · " : "";
  if (doc.files.approval) {
    return `
      <a class="btn primary" href="${esc(doc.files.approval)}" target="_blank" rel="noopener" title="${esc(PDF_LABELS.approval.tip)}">
        ${pfx}${PDF_LABELS.approval.label} <span class="arrow">↗</span></a>
      <a class="btn ghost" href="${esc(doc.files.non_approval)}" target="_blank" rel="noopener" title="${esc(PDF_LABELS.non_approval.tip)}">
        ${pfx}${PDF_LABELS.non_approval.label} <span class="arrow">↗</span></a>
      ${wordLink(doc)}`;
  }
  return `
      <a class="btn primary" href="${esc(doc.files.non_approval)}" target="_blank" rel="noopener">
        ${multi ? esc(doc.label) : "Download PDF"} <span class="arrow">↗</span></a>
      ${wordLink(doc)}`;
}

function card(p) {
  const ed = latest(p);
  const el = document.createElement("article");
  el.className = "card";
  const approvalRow = ed.approval_date
    ? `<br><b>Approved:</b> ${esc(ed.approval_date)}` : "";
  const n = p.editions.length;
  const docs = ed.documents || [];
  const multi = docs.length > 1;
  el.innerHTML = `
    <div>
      <h2 class="title">${esc(p.title)}${statusBadge(p.id)}</h2>
      <div class="tags">
        <span class="tag lang">${esc(p.language || "English")}</span>
        <span class="tag">${esc(ed.version || "Version 1")}</span>
        <span class="tag">${prettyDate(ed.date)}</span>
        ${p.category && p.category !== "Policy" ? `<span class="tag cat">${esc(p.category)}</span>` : ""}
      </div>
      <div class="info">
        <b>Owner:</b> ${esc(p.owner || "—")} &nbsp;·&nbsp; <b>Approver:</b> ${esc(p.approver || "—")}
        ${approvalRow}
        <br><b>Last updated:</b> ${prettyDate(ed.date)} &nbsp;·&nbsp;
        <b>Editions:</b> ${n}
      </div>
    </div>
    <div class="actions">
      ${docs.map(d => docLinks(d, multi)).join("")}
      <button type="button" class="btn primary edit">Request change or edit</button>
      <button type="button" class="btn ghost history">History</button>
    </div>`;
  el.querySelector(".edit").addEventListener("click", () => openEditChooser(p));
  el.querySelector(".history").addEventListener("click", () => openHistory(p));
  wireStatusActions(el, p);
  return el;
}

// ---- single edit workspace entry (PDF + notes + comment + file) -----------

function editTargets(p) {
  const ed = latest(p);
  const out = [];
  const docs = ed.documents || [];
  docs.forEach(d => {
    const base = docs.length > 1 ? d.label + " — " : "";
    if (d.files && d.files.non_approval)
      out.push({ label: base + (d.files.approval ? "Unsigned" : "PDF"), file: d.files.non_approval, variant: d.files.approval ? "Unsigned" : "", ed });
    if (d.files && d.files.approval)
      out.push({ label: base + "Signed", file: d.files.approval, variant: "Signed", ed });
    // When both signed and unsigned exist, offer a "Both" option: the requester
    // marks up the unsigned copy and the change is applied to both variants.
    if (d.files && d.files.approval && d.files.non_approval)
      out.push({ label: base + "Both (signed + unsigned)", file: d.files.non_approval, variant: "Both", ed });
  });
  return out;
}

function gotoEdit(p, t) {
  const q = new URLSearchParams({ policy: p.id, edition: edKey(t.ed), title: p.title, file: t.file });
  if (t.variant) q.set("variant", t.variant);
  location.href = "review.html?" + q.toString();
}

function openEditChooser(p) {
  const targets = editTargets(p);
  if (targets.length === 0) { alert("No document available to edit."); return; }
  if (targets.length === 1) { gotoEdit(p, targets[0]); return; }
  let dlg = document.getElementById("editChooser");
  if (!dlg) { dlg = document.createElement("dialog"); dlg.id = "editChooser"; dlg.className = "vh-dialog chooser"; document.body.appendChild(dlg); }
  dlg.innerHTML = `<div class="vh-box chooser-box">
      <h3>Which version do you want to edit?</h3>
      <p class="chooser-hint">Pick Signed or Unsigned — or "Both", and the change will be applied to both versions. You'll open the live PDF to add highlights, a comment and a file, then send.</p>
      <div class="chooser-list">${targets.map((t, i) => `<button type="button" class="btn primary" data-i="${i}">${esc(t.label)} ↗</button>`).join("")}</div>
      <button type="button" class="btn ghost chooser-x">Cancel</button>
    </div>`;
  dlg.querySelectorAll("[data-i]").forEach(b =>
    b.addEventListener("click", () => { dlg.close(); gotoEdit(p, targets[+b.dataset.i]); }));
  dlg.querySelector(".chooser-x").addEventListener("click", () => dlg.close());
  if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
}

// ---- change-request status badge + actions -------------------------------

function statusBadge(id) {
  const st = PENDING.get(id);
  if (st === "change_pending") return ' <span class="pending-badge change">Change pending</span>';
  if (st === "pending_review") return ' <span class="pending-badge review">Pending for review</span>';
  return "";
}

function wireStatusActions(el, p) {
  const st = PENDING.get(p.id);
  if (!st) return;
  const badge = el.querySelector(".pending-badge");
  const actions = el.querySelector(".actions");

  // Admin can mark the change "done" -> moves it to the requester for review.
  if (st === "change_pending" && IS_ADMIN) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "btn ghost"; b.textContent = "Mark changes done → review";
    b.addEventListener("click", () => pendingAction(p.id, "review"));
    actions.appendChild(b);
  }
  // Anyone reviewing can approve or ask for another round once changes are done.
  if (st === "pending_review") {
    const ap = document.createElement("button");
    ap.type = "button"; ap.className = "btn primary"; ap.textContent = "Approve changes";
    ap.addEventListener("click", () => {
      if (confirm(`Approve the changes to "${p.title}"? This clears the request.`)) pendingAction(p.id, "approve");
    });
    const re = document.createElement("button");
    re.type = "button"; re.className = "btn ghost"; re.textContent = "Request another round";
    re.addEventListener("click", () => pendingAction(p.id, "reopen"));
    actions.appendChild(ap); actions.appendChild(re);
  }
  if (badge && IS_ADMIN) {
    badge.classList.add("clickable");
    badge.title = "Clear request";
    badge.addEventListener("click", async () => {
      if (!confirm(`Clear the change request for "${p.title}"?`)) return;
      await fetch("api/pending", { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ policy: p.id }) });
      await loadPendingChanges();
    });
  }
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

function metaItem(k, v) {
  return v ? `<div class="vh-mitem"><span class="vh-mk">${esc(k)}</span><span class="vh-mv">${v}</span></div>` : "";
}

function editionPanel(p, ed, isLatest) {
  const docsHtml = (ed.documents || []).map(doc => `
    <div class="vh-doc">
      <span class="vh-doclabel">${esc(doc.label)}</span>
      ${doc.files.approval ? `<a class="vh-dl" href="${esc(doc.files.approval)}" target="_blank" rel="noopener" title="${esc(PDF_LABELS.approval.tip)}">Signed PDF ↗</a>` : ""}
      <a class="vh-dl" href="${esc(doc.files.non_approval)}" target="_blank" rel="noopener" title="${esc(PDF_LABELS.non_approval.tip)}">${doc.files.approval ? "Unsigned PDF" : "PDF"} ↗</a>
      ${doc.files.word ? `<a class="vh-dl word" href="${esc(doc.files.word)}" download title="Editable Word (.docx) copy">Word ↓</a>` : ""}
      <a class="vh-dl" href="${esc(annHref(p, ed, doc.files.non_approval))}" title="See the comments &amp; highlights captured on this version">Highlights ↗</a>
    </div>`).join("");
  return `
    <div class="vh-ed-head">
      <span class="vh-version">${esc(ed.version || "Version 1")}</span>
      ${isLatest ? '<span class="vh-current">Current</span>' : '<span class="vh-archived">Archived</span>'}
    </div>
    <div class="vh-meta-grid">
      ${metaItem("Published", prettyDate(ed.date))}
      ${metaItem("Approved", ed.approval_date ? esc(ed.approval_date) : "")}
      ${metaItem("Requested by", ed.requested_by ? esc(ed.requested_by) : "")}
      ${metaItem("Approved by", ed.approved_by ? esc(ed.approved_by) : "")}
    </div>
    ${ed.notes ? `<div class="vh-changelog"><span class="vh-cl-label">What changed in this version</span><p>${esc(ed.notes)}</p></div>` : ""}
    <div class="vh-docs-wrap"><div class="vh-sec-label">Documents</div><div class="vh-docs">${docsHtml}</div></div>
    <div class="vh-sign" data-key="${esc(edKey(ed))}">
      <div class="vh-sec-label">Signatures on this version</div>
      <div class="vh-siglist"></div>
      <button type="button" class="btn vh-signbtn">🖋 Sign this version</button>
    </div>
    <div class="vh-comments" data-key="${esc(edKey(ed))}">
      <div class="vh-sec-label">Comments on this version</div>
      <div class="vh-clist"><p class="vh-cempty">Loading…</p></div>
      <div class="vh-cform">
        <textarea class="vh-ctext" rows="2" placeholder="Add a comment for the team / AI…"></textarea>
        <div class="vh-crow">
          <button type="button" class="btn vh-cadd">Add comment</button>
          <span class="vh-cstatus"></span>
        </div>
      </div>
    </div>`;
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
  document.getElementById("reqVariantsField").style.display = isNew ? "" : "none";
  const ws = document.getElementById("reqWantSigned"); if (ws) ws.checked = true;
  const wu = document.getElementById("reqWantUnsigned"); if (wu) wu.checked = false;
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
  if (mode === "new") {
    fd.set("title", docTitle);
    const wantSigned = document.getElementById("reqWantSigned").checked;
    const wantUnsigned = document.getElementById("reqWantUnsigned").checked;
    const versions = [wantSigned && "Signed", wantUnsigned && "Unsigned"].filter(Boolean).join(" + ") || "Signed";
    fd.set("versions", versions);
  }
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

// ---- signatures ----

let SIGN_CTX = null, SIGN_TARGET = null, SIGN_HAS_INK = false;
let WALLET = [], SELECTED_WALLET = null;

async function loadWallet() {
  const wrap = document.getElementById("sgSaved");
  const list = document.getElementById("sgSavedList");
  list.innerHTML = "";
  try {
    const d = await (await fetch("api/wallet", { cache: "no-store" })).json();
    WALLET = d.signatures || [];
  } catch { WALLET = []; }
  if (!WALLET.length) { wrap.hidden = true; return; }
  wrap.hidden = false;
  list.innerHTML = WALLET.map(s =>
    `<button type="button" class="sg-thumb" data-id="${esc(s.id)}" title="${esc(s.label || "")}"><img src="${esc(s.image)}" alt="saved signature" /></button>`).join("");
  list.querySelectorAll(".sg-thumb").forEach(b => b.addEventListener("click", () => selectWallet(b)));
}

function deselectWallet() {
  SELECTED_WALLET = null;
  document.querySelectorAll(".sg-thumb.active").forEach(x => x.classList.remove("active"));
}

function selectWallet(btn) {
  const s = WALLET.find(x => x.id === btn.dataset.id);
  if (!s || !SIGN_CTX) return;
  SELECTED_WALLET = s.id;
  document.querySelectorAll(".sg-thumb.active").forEach(x => x.classList.remove("active"));
  btn.classList.add("active");
  const c = document.getElementById("sigPad");
  SIGN_CTX.clearRect(0, 0, c.width, c.height);
  const img = new Image();
  img.onload = () => {
    const scale = Math.min(c.width / img.width, c.height / img.height);
    const w = img.width * scale, h = img.height * scale;
    SIGN_CTX.drawImage(img, (c.width - w) / 2, (c.height - h) / 2, w, h);
    SIGN_HAS_INK = true;
  };
  img.src = s.image;
  const nameEl = document.getElementById("sigName");
  if (!nameEl.value && s.label) nameEl.value = s.label;
}

function initSigPad() {
  const c = document.getElementById("sigPad");
  if (!c) return;
  const ctx = c.getContext("2d");
  ctx.lineWidth = 2.4; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#1c2c44";
  SIGN_CTX = ctx;
  let drawing = false, pts = [];
  const pos = (e) => {
    const r = c.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return { x: (t.clientX - r.left) * (c.width / r.width), y: (t.clientY - r.top) * (c.height / r.height) };
  };
  const down = (e) => { drawing = true; pts = [pos(e)]; deselectWallet(); e.preventDefault(); };
  const move = (e) => {
    if (!drawing) return;
    pts.push(pos(e));
    const n = pts.length;
    if (n < 3) return;
    // Smooth: quadratic curve through the midpoints, using the real point as control.
    const p0 = pts[n - 3], p1 = pts[n - 2], p2 = pts[n - 1];
    const m1 = { x: (p0.x + p1.x) / 2, y: (p0.y + p1.y) / 2 };
    const m2 = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
    ctx.beginPath(); ctx.moveTo(m1.x, m1.y); ctx.quadraticCurveTo(p1.x, p1.y, m2.x, m2.y); ctx.stroke();
    SIGN_HAS_INK = true; e.preventDefault();
  };
  const up = (e) => {
    if (drawing && pts.length === 1) { // a single tap → a dot
      const p = pts[0]; ctx.beginPath(); ctx.arc(p.x, p.y, ctx.lineWidth / 2, 0, Math.PI * 2); ctx.fill(); SIGN_HAS_INK = true;
    }
    drawing = false;
  };
  ctx.fillStyle = "#1c2c44";
  c.addEventListener("mousedown", down); c.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  c.addEventListener("touchstart", down, { passive: false }); c.addEventListener("touchmove", move, { passive: false }); window.addEventListener("touchend", up);

  document.getElementById("sigClear").addEventListener("click", clearSig);
  document.getElementById("sigSave").addEventListener("click", saveSig);
  document.getElementById("signClose").addEventListener("click", () => { const d = document.getElementById("sign"); if (d.close) d.close(); });
  document.getElementById("sigFile").addEventListener("change", (e) => {
    const f = e.target.files[0]; if (!f) return;
    deselectWallet();
    const img = new Image();
    img.onload = () => {
      clearSig();
      const scale = Math.min(c.width / img.width, c.height / img.height);
      const w = img.width * scale, h = img.height * scale;
      ctx.drawImage(img, (c.width - w) / 2, (c.height - h) / 2, w, h);
      SIGN_HAS_INK = true; URL.revokeObjectURL(img.src);
    };
    img.src = URL.createObjectURL(f);
  });
}

function clearSig() {
  if (SIGN_CTX) { SIGN_CTX.clearRect(0, 0, 460, 170); SIGN_HAS_INK = false; }
  deselectWallet();
  const s = document.getElementById("sigStatus"); if (s) s.textContent = "";
}

function openSign(policyId, edition) {
  SIGN_TARGET = { policyId, edition };
  document.getElementById("signSub").textContent = edition.replace("__", " · ");
  clearSig();
  document.getElementById("sigName").value = "";
  const dlg = document.getElementById("sign");
  if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
  loadWallet();
}

async function saveSig() {
  const status = document.getElementById("sigStatus");
  const label = document.getElementById("sigName").value.trim();
  if (!label) { status.textContent = "Add the name / title for this signature line."; return; }
  const body = { policy: SIGN_TARGET.policyId, edition: SIGN_TARGET.edition, label };
  if (SELECTED_WALLET) {
    body.walletId = SELECTED_WALLET;
  } else {
    if (!SIGN_HAS_INK) { status.textContent = "Pick a saved signature, or draw / upload one."; return; }
    body.image = document.getElementById("sigPad").toDataURL("image/png");
  }
  const btn = document.getElementById("sigSave");
  btn.disabled = true; status.textContent = "Saving…";
  try {
    const r = await fetch("api/signatures", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    status.textContent = "Signed ✓";
    await loadSignatures(SIGN_TARGET.policyId);
    setTimeout(() => { const dlg = document.getElementById("sign"); if (dlg.close) dlg.close(); }, 900);
  } catch (e) { status.textContent = "Could not sign: " + e.message; } finally { btn.disabled = false; }
}

function renderSigList(el, sigs) {
  el.innerHTML = sigs.length
    ? '<div class="vh-siglabel">Signatures</div>' + sigs.map(s => `
      <div class="vh-sig">
        <img src="${esc(s.image)}" alt="signature" />
        <div class="vh-sigwho">
          <b>${esc(s.label || s.name)}</b>
          <span>Signed by ${esc(s.name)} (${esc(s.account)}) · ${fmtTime(s.signed_at)}</span>
        </div>
      </div>`).join("")
    : "";
}

async function loadSignatures(policyId) {
  const dlg = document.getElementById("history");
  const byEd = {};
  try {
    const d = await (await fetch(`api/signatures?policy=${encodeURIComponent(policyId)}`, { cache: "no-store" })).json();
    for (const s of (d.signatures || [])) (byEd[s.edition] = byEd[s.edition] || []).push(s);
  } catch {}
  dlg.querySelectorAll(".vh-sign").forEach(el =>
    renderSigList(el.querySelector(".vh-siglist"), byEd[el.dataset.key] || []));
}

function wireSign(p) {
  document.getElementById("history").querySelectorAll(".vh-sign").forEach(el =>
    el.querySelector(".vh-signbtn").addEventListener("click", () => openSign(p.id, el.dataset.key)));
}

function openHistory(p) {
  HISTORY_POLICY = p;
  const dlg = document.getElementById("history");
  const last = p.editions.length - 1;
  dlg.querySelector(".vh-title").textContent = `${p.title} — version history`;
  dlg.querySelector(".vh-sub").textContent =
    `${p.editions.length} version${p.editions.length !== 1 ? "s" : ""} · Owner: ${p.owner || "—"} · Approver: ${p.approver || "—"}`;
  // One tab per version, newest first.
  const tabs = dlg.querySelector(".vh-tabs");
  tabs.innerHTML = p.editions.map((ed, i) => i).reverse().map(i => {
    const ed = p.editions[i];
    return `<button type="button" class="vh-tab" data-i="${i}">
      <span class="vh-tab-v">${esc(ed.version || "Version 1")}</span>
      <span class="vh-tab-d">${esc(prettyDate(ed.date))}${i === last ? " · current" : ""}</span>
    </button>`;
  }).join("");
  tabs.querySelectorAll(".vh-tab").forEach(b =>
    b.addEventListener("click", () => showEdition(p, +b.dataset.i)));
  showEdition(p, last);
  if (typeof dlg.showModal === "function") dlg.showModal();
  else dlg.setAttribute("open", "");
}

function showEdition(p, idx) {
  const dlg = document.getElementById("history");
  dlg.querySelectorAll(".vh-tab").forEach(b => b.classList.toggle("active", +b.dataset.i === idx));
  const ed = p.editions[idx];
  dlg.querySelector(".vh-panel").innerHTML = editionPanel(p, ed, idx === p.editions.length - 1);
  wireComments(p.id);
  loadComments(p.id);
  wireSign(p);
  loadSignatures(p.id);
}

let POLICIES = [];
let SEARCH = "";
let OWNER_FILTER = "";    // "" = all
let APPROVER_FILTER = ""; // "" = all
let PENDING = new Map(); // policy id -> "change_pending" | "pending_review"
let IS_ADMIN = false;
let STATUS_FILTER = null; // null = all; else "change_pending" | "pending_review" | "approved"

// A policy with no open change request is "approved" (up to date).
function policyStatus(p) { return PENDING.get(p.id) || "approved"; }

let QUEUE = []; // admin-only: full pending entries (requester, title, status, dates)

async function loadPendingChanges() {
  try {
    const d = await (await fetch("api/pending", { cache: "no-store" })).json();
    PENDING = new Map((d.pending || []).map(x => [x.policy, x.status || "change_pending"]));
    QUEUE = d.queue || [];
  } catch { PENDING = new Map(); QUEUE = []; }
  renderStatusFilter();
  renderQueueButton();
  render();
  if (document.getElementById("queue")?.open) renderQueue();
}

function renderQueueButton() {
  const b = document.getElementById("queueBtn");
  if (!b) return;
  const open = QUEUE.filter(it => it.status && it.status !== "approved").length;
  b.hidden = !(IS_ADMIN && open > 0);
  const c = document.getElementById("queueCount");
  if (c) c.textContent = open;
}

const QSTATUS = {
  change_pending: { label: "Change pending", cls: "change" },
  pending_review: { label: "Pending for review", cls: "review" },
};

function openQueue() {
  renderQueue();
  const dlg = document.getElementById("queue");
  if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
}

function renderQueue() {
  const wrap = document.getElementById("queueList");
  const sub = document.getElementById("queueSub");
  if (!wrap) return;
  const order = { change_pending: 0, pending_review: 1 };
  const items = QUEUE.filter(it => it.status && it.status !== "approved")
    .slice().sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9) ||
      (a.created_at || 0) - (b.created_at || 0));
  sub.textContent = `${items.length} open request${items.length !== 1 ? "s" : ""}`;
  if (!items.length) { wrap.innerHTML = `<p class="vh-cempty">Nothing pending review. 🎉</p>`; return; }
  wrap.innerHTML = items.map((it, i) => {
    const p = POLICIES.find(x => x.id === it.policy);
    const s = QSTATUS[it.status] || { label: it.status, cls: "change" };
    const when = it.created_at ? fmtTime(new Date(it.created_at).toISOString()) : "";
    const who = esc(it.author || "—") + (it.email ? ` · ${esc(it.email)}` : "");
    return `<div class="queue-item" data-i="${i}">
      <div class="queue-main">
        <div class="queue-top">
          <span class="queue-policy">${esc(p ? p.title : it.policy)}</span>
          <span class="pending-badge ${s.cls}">${esc(s.label)}</span>
        </div>
        <div class="queue-meta">Requested by ${who}${when ? " · " + esc(when) : ""}</div>
      </div>
      <div class="queue-actions">
        <button type="button" class="btn ghost" data-act="edit" data-i="${i}">Open editor</button>
        ${it.status === "change_pending"
          ? `<button type="button" class="btn primary" data-act="review" data-i="${i}">Mark done → review</button>`
          : `<button type="button" class="btn primary" data-act="approve" data-i="${i}">Approve</button>
             <button type="button" class="btn ghost" data-act="reopen" data-i="${i}">Another round</button>`}
      </div>
    </div>`;
  }).join("");
  wrap.querySelectorAll("[data-act]").forEach(btn => btn.addEventListener("click", async () => {
    const it = items[+btn.dataset.i];
    const p = POLICIES.find(x => x.id === it.policy);
    const act = btn.dataset.act;
    if (act === "edit") { if (p) openEditChooser(p); return; }
    if (act === "approve" && !confirm(`Approve the changes to "${p ? p.title : it.policy}"? This clears the request.`)) return;
    btn.disabled = true;
    await pendingAction(it.policy, act);   // reloads pending + re-renders the queue
  }));
}

async function pendingAction(policy, action) {
  await fetch("api/pending", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy, action }),
  });
  await loadPendingChanges();
}

function render() {
  const list = document.getElementById("list");
  const f = SEARCH.trim().toLowerCase();
  let shown = POLICIES.filter(p => {
    if (OWNER_FILTER && (p.owner || "") !== OWNER_FILTER) return false;
    if (APPROVER_FILTER && (p.approver || "") !== APPROVER_FILTER) return false;
    if (STATUS_FILTER && policyStatus(p) !== STATUS_FILTER) return false;
    if (!f) return true;
    return p.title.toLowerCase().includes(f) || (p.owner || "").toLowerCase().includes(f) ||
      (p.approver || "").toLowerCase().includes(f) || (p.language || "").toLowerCase().includes(f) ||
      (p.group || "").toLowerCase().includes(f);
  });
  // Cluster family members together (under a section header), keep the rest alphabetical.
  shown = shown.slice().sort((a, b) => {
    const ka = (a.group || a.title).toLowerCase(), kb = (b.group || b.title).toLowerCase();
    return ka < kb ? -1 : ka > kb ? 1 : a.title.localeCompare(b.title);
  });
  list.innerHTML = "";
  let curGroup = null;
  shown.forEach(p => {
    if (p.group && p.group !== curGroup) {
      const h = document.createElement("div");
      h.className = "family-head";
      h.innerHTML = `${esc(p.group)} <span class="family-count">family</span>`;
      list.appendChild(h);
      curGroup = p.group;
    } else if (!p.group) {
      curGroup = null;
    }
    list.appendChild(card(p));
  });
  document.getElementById("empty").hidden = shown.length > 0;
  document.getElementById("count").textContent =
    `${shown.length} of ${POLICIES.length} policies`;
}

function renderStatusFilter() {
  const el = document.getElementById("statusfilter");
  if (!el) return;
  const defs = [
    ["change_pending", "Change pending"],
    ["pending_review", "Pending for review"],
    ["approved", "Up to date"],
  ];
  const count = (s) => POLICIES.filter(p => policyStatus(p) === s).length;
  const isActive = (val) => val === "__all" ? STATUS_FILTER === null : STATUS_FILTER === val;
  const btn = (val, label, n) =>
    `<button type="button" class="sfilter sf-${esc(val)}${isActive(val) ? " active" : ""}" data-val="${esc(val)}">${esc(label)} <span class="sf-count">${n}</span></button>`;
  el.innerHTML =
    '<span class="chips-label">Status</span>' +
    btn("__all", "All", POLICIES.length) +
    defs.map(([v, l]) => btn(v, l, count(v))).join("");
  el.querySelectorAll(".sfilter").forEach(b => b.addEventListener("click", () => {
    const v = b.dataset.val;
    STATUS_FILTER = (v === "__all" || STATUS_FILTER === v) ? null : v;
    renderStatusFilter(); render();
  }));
}

function renderChips() {
  const el = document.getElementById("chips");
  const uniq = (k) => [...new Set(POLICIES.map(p => p[k]).filter(Boolean))].sort();
  const opts = (vals, sel) => `<option value="">All</option>` +
    vals.map(v => `<option value="${esc(v)}"${v === sel ? " selected" : ""}>${esc(v)}</option>`).join("");
  const active = OWNER_FILTER || APPROVER_FILTER;
  el.innerHTML =
    `<label class="fdrop"><span class="fdrop-label">Owner</span>
       <select id="ownerSel" class="fselect">${opts(uniq("owner"), OWNER_FILTER)}</select></label>
     <label class="fdrop"><span class="fdrop-label">Approver</span>
       <select id="approverSel" class="fselect">${opts(uniq("approver"), APPROVER_FILTER)}</select></label>` +
    (active ? `<button type="button" id="filterClear" class="chip clear">Clear ✕</button>` : "");
  el.querySelector("#ownerSel").addEventListener("change", e => { OWNER_FILTER = e.target.value; renderChips(); render(); });
  el.querySelector("#approverSel").addEventListener("change", e => { APPROVER_FILTER = e.target.value; renderChips(); render(); });
  const clr = el.querySelector("#filterClear");
  if (clr) clr.addEventListener("click", () => { OWNER_FILTER = ""; APPROVER_FILTER = ""; renderChips(); render(); });
}

// Show a count of open requests (new-policy + pending) on the Requests button.
async function loadOpenRequestCount() {
  try {
    const d = await (await fetch("api/admin/requests", { cache: "no-store" })).json();
    const open = (d.requests || []).filter(r => r.current_status !== "done").length;
    const b = document.getElementById("reqCount");
    if (b) { b.textContent = open; b.hidden = open === 0; }
  } catch {}
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
  IS_ADMIN = me.role === "admin";
  const reqLink = document.getElementById("requestsLink");
  if (reqLink) reqLink.hidden = !IS_ADMIN;
  if (IS_ADMIN) loadOpenRequestCount();
  document.getElementById("acctName").textContent = me.name;
  const logout = document.getElementById("logoutBtn");
  logout.hidden = false;
  logout.addEventListener("click", async () => {
    try { await fetch("api/auth/logout", { method: "POST" }); } catch {}
    location.href = "/login";
  });
  if (IS_ADMIN) setupAdmin();
  else setupVisitorBell();
  render();
}

// ---- visitor notification bell (status of their own change requests) ----

function statusLabel(s) {
  return s === "pending_review" ? "Ready for your review"
    : s === "change_pending" ? "In progress" : s;
}

async function myRequests() {
  try { return (await (await fetch("api/my-requests", { cache: "no-store" })).json()).requests || []; }
  catch { return []; }
}

async function setupVisitorBell() {
  const bell = document.getElementById("bellBtn");
  if (!bell) return;
  bell.hidden = false;
  bell.title = "My change requests";
  bell.addEventListener("click", openMyRequests);
  const reqs = await myRequests();
  const ready = reqs.filter(r => r.status === "pending_review").length;
  const b = document.getElementById("bellBadge");
  if (ready > 0) { b.hidden = false; b.textContent = ready > 99 ? "99+" : ready; } else b.hidden = true;
}

async function openMyRequests() {
  const reqs = await myRequests();
  let dlg = document.getElementById("myReqs");
  if (!dlg) { dlg = document.createElement("dialog"); dlg.id = "myReqs"; dlg.className = "vh-dialog chooser"; document.body.appendChild(dlg); }
  dlg.innerHTML = `<div class="vh-box chooser-box">
      <h3>My change requests</h3>
      ${reqs.length ? reqs.map(r => `
        <div class="myreq myreq-${esc(r.status)}">
          <span class="myreq-title">${esc(r.title || r.policy)}</span>
          <span class="myreq-status">${esc(statusLabel(r.status))}</span>
        </div>`).join("")
      : '<p class="chooser-hint">You have no open change requests.</p>'}
      <button type="button" class="btn ghost chooser-x">Close</button>
    </div>`;
  dlg.querySelector(".chooser-x").addEventListener("click", () => dlg.close());
  if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
}

async function setupAdmin() {
  document.getElementById("connectBtn").hidden = false; // admin-only
  const hint = document.getElementById("adminHint"); if (hint) hint.hidden = false;
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
    renderChips();
    renderStatusFilter();
    render();
    document.getElementById("search").addEventListener("input", e => { SEARCH = e.target.value; render(); });
    const connectBtn = document.getElementById("connectBtn");
    const connectDlg = document.getElementById("connect");
    if (connectBtn && connectDlg) {
      connectBtn.addEventListener("click", () => {
        if (typeof connectDlg.showModal === "function") connectDlg.showModal();
        else connectDlg.setAttribute("open", "");
      });
    }
    const queueBtn = document.getElementById("queueBtn");
    if (queueBtn) queueBtn.addEventListener("click", openQueue);
    const queueClose = document.getElementById("queueClose");
    if (queueClose) queueClose.addEventListener("click", () => {
      const d = document.getElementById("queue"); if (d.close) d.close(); else d.removeAttribute("open");
    });
    document.getElementById("newReqBtn").addEventListener("click", () => openRequest("new"));
    document.getElementById("reqClose").addEventListener("click",
      () => { const d = document.getElementById("request"); if (d.close) d.close(); });
    document.getElementById("reqSubmit").addEventListener("click", submitRequest);
    initSigPad();
    setupAccount();
    loadPendingChanges();
  } catch (err) {
    const e = document.getElementById("error");
    e.hidden = false;
    e.textContent = "Could not load library.json. Serve this folder over HTTP " +
      "(e.g. `python -m http.server` in docs/, or via GitHub Pages).";
  }
}

init();
