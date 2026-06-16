// BioMar Policy Library — PDF review & annotate view.
// Renders a policy PDF with PDF.js, lets the user select text and attach a note
// that is highlighted and saved to the repo (via /api/annotations) so a
// connected AI agent can read the exact quoted passage.

const SCALE = 1.35;
const CDN = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174";

const params = new URLSearchParams(location.search);
const FILE = params.get("file") || "";
const POLICY = params.get("policy") || "";
const EDITION = params.get("edition") || "";
const TITLE = params.get("title") || "Document";

const viewer = document.getElementById("viewer");
const selBtn = document.getElementById("selBtn");
const composer = document.getElementById("composer");
const cQuote = document.getElementById("cQuote");
const cText = document.getElementById("cText");
const cStatus = document.getElementById("cStatus");
const annListEl = document.getElementById("annList");
const annEmpty = document.getElementById("annEmpty");
const annCount = document.getElementById("annCount");

const pages = [];          // { n, cont, overlay, w, h }
let annotations = [];
let pendingAnchor = null;   // { page, rects, quote }

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtTime(iso) {
  const d = new Date(iso);
  return isNaN(d) ? esc(iso) : d.toLocaleString(undefined,
    { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function showError(msg) {
  const e = document.getElementById("loadErr");
  e.hidden = false; e.textContent = msg;
}

// ---- render the PDF ------------------------------------------------------

async function renderPdf() {
  if (!window.pdfjsLib) { showError("PDF viewer failed to load."); return false; }
  if (!/^files\/[A-Za-z0-9._-]+\.pdf$/.test(FILE)) { showError("Invalid document."); return false; }
  pdfjsLib.GlobalWorkerOptions.workerSrc = `${CDN}/pdf.worker.min.js`;

  let pdf;
  try {
    pdf = await pdfjsLib.getDocument(FILE).promise;
  } catch (e) {
    showError("Could not load the PDF (" + (e && e.message ? e.message : e) + ").");
    return false;
  }

  for (let n = 1; n <= pdf.numPages; n++) {
    const page = await pdf.getPage(n);
    const viewport = page.getViewport({ scale: SCALE });
    const cont = document.createElement("div");
    cont.className = "rv-page";
    cont.dataset.page = String(n);
    cont.style.width = viewport.width + "px";
    cont.style.height = viewport.height + "px";

    const canvas = document.createElement("canvas");
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    cont.appendChild(canvas);

    const badge = document.createElement("span");
    badge.className = "rv-pagenum";
    badge.textContent = "p. " + n;
    cont.appendChild(badge);

    const overlay = document.createElement("div");
    overlay.className = "rv-hloverlay";
    cont.appendChild(overlay);

    const textLayer = document.createElement("div");
    textLayer.className = "textLayer";
    cont.appendChild(textLayer);

    viewer.appendChild(cont);

    await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
    const textContent = await page.getTextContent();
    pdfjsLib.renderTextLayer({ textContentSource: textContent, container: textLayer, viewport, textDivs: [] });

    pages.push({ n, cont, overlay, w: viewport.width, h: viewport.height });
  }
  return true;
}

// ---- selection -> anchor -------------------------------------------------

function pageElAt(x, y) {
  for (const p of pages) {
    const r = p.cont.getBoundingClientRect();
    if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return p.cont;
  }
  return null;
}

function computeAnchor(range) {
  const byPage = new Map();
  for (const cr of range.getClientRects()) {
    if (cr.width < 1 || cr.height < 1) continue;
    const pageEl = pageElAt(cr.left + cr.width / 2, cr.top + cr.height / 2);
    if (!pageEl) continue;
    const pr = pageEl.getBoundingClientRect();
    const n = parseInt(pageEl.dataset.page, 10);
    if (!byPage.has(n)) byPage.set(n, []);
    byPage.get(n).push({
      x: (cr.left - pr.left) / pr.width,
      y: (cr.top - pr.top) / pr.height,
      w: cr.width / pr.width,
      h: cr.height / pr.height,
    });
  }
  let bestPage = null, bestRects = [];
  for (const [n, rs] of byPage) if (rs.length > bestRects.length) { bestPage = n; bestRects = rs; }
  return bestPage ? { page: bestPage, rects: bestRects } : null;
}

function hideSelBtn() { selBtn.hidden = true; }

function onSelection() {
  if (!composer.hidden) return;
  const sel = window.getSelection();
  const quote = sel ? sel.toString().trim() : "";
  if (!sel || sel.isCollapsed || !quote) { hideSelBtn(); return; }
  const range = sel.getRangeAt(0);
  if (!viewer.contains(range.commonAncestorContainer)) { hideSelBtn(); return; }
  const anchor = computeAnchor(range);
  if (!anchor) { hideSelBtn(); return; }
  pendingAnchor = { ...anchor, quote };
  const rects = range.getClientRects();
  const r = rects[rects.length - 1];
  selBtn.style.left = (window.scrollX + r.right + 6) + "px";
  selBtn.style.top = (window.scrollY + r.top - 6) + "px";
  selBtn.hidden = false;
}

// ---- composer ------------------------------------------------------------

function openComposer() {
  if (!pendingAnchor) return;
  cQuote.textContent = "“" + pendingAnchor.quote.slice(0, 400) + "”";
  cText.value = "";
  cStatus.textContent = "";
  composer.style.left = selBtn.style.left;
  composer.style.top = (parseFloat(selBtn.style.top) + 26) + "px";
  selBtn.hidden = true;
  composer.hidden = false;
  cText.focus();
}

function closeComposer() {
  composer.hidden = true;
  const s = window.getSelection();
  if (s) s.removeAllRanges();
  pendingAnchor = null;
}

async function saveNote() {
  const text = cText.value.trim();
  if (!text) { cStatus.textContent = "Write a note first."; return; }
  if (!pendingAnchor) { cStatus.textContent = "Select text again."; return; }
  const saveBtn = document.getElementById("cSave");
  saveBtn.disabled = true; cStatus.textContent = "Saving…";
  try {
    const r = await fetch("api/annotations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        policy: POLICY, file: FILE, edition: EDITION,
        page: pendingAnchor.page, quote: pendingAnchor.quote,
        rects: pendingAnchor.rects, text,
      }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    annotations.push(d.annotation);
    drawHighlight(d.annotation);
    renderSidebar();
    closeComposer();
  } catch (e) {
    cStatus.textContent = "Could not save: " + e.message;
    saveBtn.disabled = false;
  } finally {
    saveBtn.disabled = false;
  }
}

// ---- highlights + sidebar ------------------------------------------------

function drawHighlight(ann) {
  const page = pages.find(p => p.n === ann.page);
  if (!page || !Array.isArray(ann.rects)) return;
  for (const rc of ann.rects) {
    const hl = document.createElement("div");
    hl.className = "rv-hl";
    hl.dataset.id = ann.id;
    hl.style.left = (rc.x * page.w) + "px";
    hl.style.top = (rc.y * page.h) + "px";
    hl.style.width = (rc.w * page.w) + "px";
    hl.style.height = (rc.h * page.h) + "px";
    hl.title = ann.text;
    hl.addEventListener("click", () => focusAnn(ann.id, true));
    page.overlay.appendChild(hl);
  }
}

function focusAnn(id, fromDoc) {
  document.querySelectorAll(".rv-hl.active, .rv-ann.active")
    .forEach(el => el.classList.remove("active"));
  document.querySelectorAll(`.rv-hl[data-id="${id}"]`).forEach(el => el.classList.add("active"));
  const card = annListEl.querySelector(`.rv-ann[data-id="${id}"]`);
  if (card) {
    card.classList.add("active");
    if (fromDoc) card.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  if (!fromDoc) {
    const hl = document.querySelector(`.rv-hl[data-id="${id}"]`);
    if (hl) hl.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function renderSidebar() {
  const sorted = annotations.slice().sort(
    (a, b) => (a.page - b.page) || (a.created_at < b.created_at ? -1 : 1));
  annListEl.innerHTML = sorted.map(a => `
    <div class="rv-ann" data-id="${esc(a.id)}">
      <div class="pg">Page ${esc(a.page)}</div>
      ${a.quote ? `<p class="q">“${esc(a.quote.slice(0, 220))}”</p>` : ""}
      <p class="tx">${esc(a.text)}</p>
      <div class="by">${esc(a.author || "Anonymous")} · ${fmtTime(a.created_at)}</div>
    </div>`).join("");
  annListEl.querySelectorAll(".rv-ann").forEach(el =>
    el.addEventListener("click", () => focusAnn(el.dataset.id, false)));
  annCount.textContent = annotations.length ? `${annotations.length}` : "";
  annEmpty.hidden = annotations.length > 0;
}

async function loadAnnotations() {
  try {
    const r = await fetch(
      `api/annotations?policy=${encodeURIComponent(POLICY)}&file=${encodeURIComponent(FILE)}`,
      { cache: "no-store" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    annotations = d.annotations || [];
  } catch (e) {
    annEmpty.hidden = false;
    annEmpty.innerHTML = `Annotations unavailable (${esc(e.message)}). You can still read the document.`;
    return;
  }
  annotations.forEach(drawHighlight);
  renderSidebar();
}

// ---- init ----------------------------------------------------------------

async function init() {
  document.getElementById("docTitle").textContent = TITLE;
  document.getElementById("docSub").textContent =
    (EDITION ? EDITION.replace("__", " · ") + " — " : "") + "Select text, then add a note.";
  document.title = `BioMar · Review — ${TITLE}`;

  selBtn.addEventListener("click", openComposer);
  document.getElementById("cSave").addEventListener("click", saveNote);
  document.getElementById("cCancel").addEventListener("click", closeComposer);
  document.addEventListener("mouseup", () => setTimeout(onSelection, 0));
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeComposer(); });

  const ok = await renderPdf();
  if (ok) await loadAnnotations();
}

init();
