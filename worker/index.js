// BioMar Policy Library — edge auth gate + comments/annotations API.
//
// This Worker runs in front of the static assets (docs/) and:
//   1. Protects the whole site with HTTP Basic Auth (username + password).
//   2. Serves small JSON APIs backed by the GitHub repository so reader feedback
//      persists as files an AI agent connected to the repo can later read:
//        - /api/comments     -> policies/comments/<id>.json     (per version)
//        - /api/annotations  -> policies/annotations/<id>.json  (anchored to PDF text)
//        - /api/requests     -> policies/requests/<id>/...      (change / new-policy
//                               requests with an optional .docx/.pdf upload; also
//                               opens a GitHub issue and sends an email)
//
// Environment:
//   AUTH_USER, AUTH_PASS  (secrets)  — login credentials.
//   GH_TOKEN              (secret)   — GitHub token with contents:read+write AND issues:write.
//   RESEND_API_KEY        (secret)   — optional; enables email notifications.
//   GH_OWNER, GH_REPO, GH_BRANCH (vars) — where feedback is committed.
//   NOTIFY_EMAIL, RESEND_FROM    (vars) — email notification target / sender.
//
// Fail closed: with no AUTH_USER/AUTH_PASS the site is not served. With no
// GH_TOKEN the feedback APIs return 503 but the catalogue still works. Issue +
// email notifications are best-effort (a request still saves if they fail).

const REALM = "BioMar Policy Library";
const COMMENTS_DIR = "policies/comments";
const ANNOTATIONS_DIR = "policies/annotations";
const REQUESTS_DIR = "policies/requests";
const MAX_TEXT = 4000;
const MAX_QUOTE = 1000;
const MAX_AUTHOR = 120;
const MAX_RECTS = 80;
const MAX_FILE = 12 * 1024 * 1024; // 12 MB upload cap

// ---- auth ----------------------------------------------------------------

function unauthorized() {
  return new Response("Authentication required.", {
    status: 401,
    headers: {
      "WWW-Authenticate": `Basic realm="${REALM}", charset="UTF-8"`,
      "Cache-Control": "no-store",
    },
  });
}

function safeEqual(a, b) {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  let diff = ab.length ^ bb.length;
  const len = Math.max(ab.length, bb.length);
  for (let i = 0; i < len; i++) diff |= (ab[i] || 0) ^ (bb[i] || 0);
  return diff === 0;
}

function authedUser(request, env) {
  const user = env.AUTH_USER;
  const pass = env.AUTH_PASS;
  if (!user || !pass) return { configured: false };
  const header = request.headers.get("Authorization") || "";
  const [scheme, encoded] = header.split(" ");
  if (scheme !== "Basic" || !encoded) return { configured: true, ok: false };
  let decoded;
  try { decoded = atob(encoded); } catch { return { configured: true, ok: false }; }
  const sep = decoded.indexOf(":");
  if (sep < 0) return { configured: true, ok: false };
  const okUser = safeEqual(decoded.slice(0, sep), user);
  const okPass = safeEqual(decoded.slice(sep + 1), pass);
  return { configured: true, ok: okUser && okPass, name: decoded.slice(0, sep) };
}

// ---- base64 (UTF-8 safe) -------------------------------------------------

function b64encode(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function b64decode(b64) {
  const bin = atob(b64.replace(/\s/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

// ---- GitHub helpers ------------------------------------------------------

function ghHeaders(env) {
  return {
    "Authorization": `Bearer ${env.GH_TOKEN}`,
    "Accept": "application/vnd.github+json",
    "User-Agent": "biomar-policy-library",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

function contentsUrl(env, path) {
  return `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/contents/${path}`;
}

async function ghGetList(env, path) {
  const url = `${contentsUrl(env, path)}?ref=${encodeURIComponent(env.GH_BRANCH)}`;
  const r = await fetch(url, { headers: ghHeaders(env) });
  if (r.status === 404) return { list: [], sha: null };
  if (!r.ok) throw new Error(`GitHub GET ${r.status}: ${await r.text()}`);
  const data = await r.json();
  let list = [];
  try { list = JSON.parse(b64decode(data.content)); } catch { list = []; }
  if (!Array.isArray(list)) list = [];
  return { list, sha: data.sha };
}

async function ghPutList(env, path, list, sha, message) {
  const body = {
    message,
    content: b64encode(JSON.stringify(list, null, 2) + "\n"),
    branch: env.GH_BRANCH,
  };
  if (sha) body.sha = sha;
  return fetch(contentsUrl(env, path), {
    method: "PUT",
    headers: { ...ghHeaders(env), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// Append an item to a repo JSON array with a small retry on SHA conflict.
async function appendItem(env, path, item, message) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const { list, sha } = await ghGetList(env, path);
    list.push(item);
    const r = await ghPutList(env, path, list, sha, message);
    if (r.ok) return { ok: true };
    if (r.status === 409 || r.status === 422) continue; // sha conflict → retry
    return { ok: false, status: r.status };
  }
  return { ok: false, status: 409 };
}

// base64 of raw bytes (for binary uploads).
function bytesToB64(bytes) {
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

// Create a brand-new file in the repo (no sha; expects a unique path).
async function ghCreateFile(env, path, contentB64, message) {
  return fetch(contentsUrl(env, path), {
    method: "PUT",
    headers: { ...ghHeaders(env), "Content-Type": "application/json" },
    body: JSON.stringify({ message, content: contentB64, branch: env.GH_BRANCH }),
  });
}

// Open a GitHub issue (best-effort; needs Issues:write on the token).
async function ghCreateIssue(env, title, body, labels) {
  const url = `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/issues`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...ghHeaders(env), "Content-Type": "application/json" },
    body: JSON.stringify({ title, body, labels }),
  });
  if (!r.ok) return { ok: false, status: r.status };
  const d = await r.json();
  return { ok: true, number: d.number, url: d.html_url };
}

// Send an email via Resend (best-effort; needs RESEND_API_KEY + NOTIFY_EMAIL).
async function sendEmail(env, subject, html) {
  if (!env.RESEND_API_KEY || !env.NOTIFY_EMAIL) return { ok: false, skipped: true };
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { "Authorization": `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.RESEND_FROM || "BioMar Policies <onboarding@resend.dev>",
      to: [env.NOTIFY_EMAIL],
      subject,
      html,
    }),
  });
  return { ok: r.ok, status: r.status };
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function safeUploadName(name) {
  const base = String(name || "upload").split(/[\\/]/).pop().slice(-120);
  const cleaned = base.replace(/[^A-Za-z0-9._-]/g, "_");
  return /\.(docx|pdf)$/i.test(cleaned) ? cleaned : null;
}

// ---- shared helpers ------------------------------------------------------

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

function safePolicyId(id) {
  return typeof id === "string" && /^[a-z0-9-]{1,80}$/.test(id) ? id : null;
}

function safeFile(f) {
  return typeof f === "string" && /^files\/[A-Za-z0-9._-]+\.pdf$/.test(f) ? f : null;
}

function missingEnv(env) {
  return ["GH_TOKEN", "GH_OWNER", "GH_REPO", "GH_BRANCH"].filter(k => !env[k]);
}

function clamp01(n) {
  n = Number(n);
  if (!isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

function cleanRects(input) {
  if (!Array.isArray(input)) return [];
  return input.slice(0, MAX_RECTS).map(r => ({
    x: clamp01(r.x), y: clamp01(r.y), w: clamp01(r.w), h: clamp01(r.h),
  }));
}

// ---- /api/comments (per-version) -----------------------------------------

async function handleComments(request, env, auth) {
  { const miss = missingEnv(env); if (miss.length) return json({ error: "Comments backend not configured. Missing: " + miss.join(", ") }, 503); }
  const url = new URL(request.url);

  if (request.method === "GET") {
    const id = safePolicyId(url.searchParams.get("policy"));
    if (!id) return json({ error: "Invalid policy id." }, 400);
    const { list } = await ghGetList(env, `${COMMENTS_DIR}/${id}.json`);
    return json({ comments: list });
  }

  if (request.method === "POST") {
    let p;
    try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    const id = safePolicyId(p.policy);
    if (!id) return json({ error: "Invalid policy id." }, 400);
    const edition = String(p.edition || "").slice(0, 200);
    const text = String(p.text || "").trim().slice(0, MAX_TEXT);
    const author = String(p.author || auth.name || "Anonymous").trim().slice(0, MAX_AUTHOR) || "Anonymous";
    if (!edition) return json({ error: "Missing edition." }, 400);
    if (!text) return json({ error: "Comment text is required." }, 400);

    const comment = { id: crypto.randomUUID(), edition, author, text, created_at: new Date().toISOString() };
    const res = await appendItem(env, `${COMMENTS_DIR}/${id}.json`, comment, `Add comment on ${id} (${edition})`);
    if (!res.ok) return json({ error: `GitHub write failed (${res.status}).` }, 502);
    return json({ comment }, 201);
  }

  return json({ error: "Method not allowed." }, 405);
}

// ---- /api/annotations (anchored to PDF text) -----------------------------

async function handleAnnotations(request, env, auth) {
  { const miss = missingEnv(env); if (miss.length) return json({ error: "Annotations backend not configured. Missing: " + miss.join(", ") }, 503); }
  const url = new URL(request.url);

  if (request.method === "GET") {
    const id = safePolicyId(url.searchParams.get("policy"));
    if (!id) return json({ error: "Invalid policy id." }, 400);
    const { list } = await ghGetList(env, `${ANNOTATIONS_DIR}/${id}.json`);
    const file = url.searchParams.get("file");
    const filtered = file ? list.filter(a => a.file === file) : list;
    return json({ annotations: filtered });
  }

  if (request.method === "POST") {
    let p;
    try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    const id = safePolicyId(p.policy);
    if (!id) return json({ error: "Invalid policy id." }, 400);
    const file = safeFile(p.file);
    if (!file) return json({ error: "Invalid file." }, 400);
    const page = parseInt(p.page, 10);
    if (!(page >= 1 && page <= 5000)) return json({ error: "Invalid page." }, 400);
    const quote = String(p.quote || "").trim().slice(0, MAX_QUOTE);
    const text = String(p.text || "").trim().slice(0, MAX_TEXT);
    const author = String(p.author || auth.name || "Anonymous").trim().slice(0, MAX_AUTHOR) || "Anonymous";
    const rects = cleanRects(p.rects);
    if (!text) return json({ error: "Comment text is required." }, 400);

    const ann = {
      id: crypto.randomUUID(),
      file, page, quote, rects,
      edition: String(p.edition || "").slice(0, 200),
      author, text,
      created_at: new Date().toISOString(),
    };
    const res = await appendItem(env, `${ANNOTATIONS_DIR}/${id}.json`, ann,
      `Add annotation on ${id} (${file} p.${page})`);
    if (!res.ok) return json({ error: `GitHub write failed (${res.status}).` }, 502);
    return json({ annotation: ann }, 201);
  }

  return json({ error: "Method not allowed." }, 405);
}

// ---- /api/requests (change / new-policy requests, with optional upload) --

async function handleRequests(request, env, auth) {
  const miss = missingEnv(env);
  if (miss.length) return json({ error: "Requests backend not configured. Missing: " + miss.join(", ") }, 503);
  if (request.method !== "POST") return json({ error: "Method not allowed." }, 405);

  let form;
  try { form = await request.formData(); } catch { return json({ error: "Invalid form data." }, 400); }

  const kind = form.get("kind") === "new" ? "new" : "change";
  const author = String(form.get("author") || auth.name || "").trim().slice(0, MAX_AUTHOR);
  const email = String(form.get("email") || "").trim().slice(0, 200);
  const title = String(form.get("title") || "").trim().slice(0, 300);
  const policy = safePolicyId(form.get("policy")) || "";
  const edition = String(form.get("edition") || "").slice(0, 200);
  const details = String(form.get("details") || "").trim().slice(0, MAX_TEXT);

  if (!author) return json({ error: "Your name is required." }, 400);
  if (!details) return json({ error: "Please describe your request." }, 400);
  if (kind === "new" && !title) return json({ error: "A title for the new policy is required." }, 400);

  const id = crypto.randomUUID();
  const warnings = [];
  let uploadPath = null;

  // Optional uploaded document → committed to the repo.
  const file = form.get("file");
  if (file && typeof file === "object" && file.size > 0) {
    if (file.size > MAX_FILE) return json({ error: "File too large (max 12 MB)." }, 400);
    const name = safeUploadName(file.name);
    if (!name) return json({ error: "Only .docx or .pdf files are allowed." }, 400);
    const bytes = new Uint8Array(await file.arrayBuffer());
    uploadPath = `${REQUESTS_DIR}/${id}/${name}`;
    const r = await ghCreateFile(env, uploadPath, bytesToB64(bytes), `Request ${id}: upload ${name}`);
    if (!r.ok) return json({ error: `Could not store the uploaded file (${r.status}).` }, 502);
  }

  const record = {
    id, kind, status: "open",
    title: kind === "new" ? title : (policy || title),
    policy, edition, author, email, details,
    upload: uploadPath,
    created_at: new Date().toISOString(),
  };

  // GitHub issue (best-effort).
  const heading = kind === "new" ? "New policy request" : "Policy change request";
  const issueTitle = kind === "new" ? `New policy: ${title}` : `Change: ${policy || title}`;
  const issueBody =
    `**${heading}**\n\n` +
    `- **Requested by:** ${author}${email ? ` (${email})` : ""}\n` +
    (kind === "new" ? `- **Proposed title:** ${title}\n` : `- **Policy:** ${policy || "—"}\n`) +
    (edition ? `- **Edition:** ${edition}\n` : "") +
    (uploadPath ? `- **Attached document:** \`${uploadPath}\`\n` : "") +
    `- **Request record:** \`${REQUESTS_DIR}/${id}/request.json\`\n\n` +
    `---\n\n${details}\n`;
  const issue = await ghCreateIssue(env, issueTitle, issueBody,
    ["policy-request", kind === "new" ? "new-policy" : "change-request"]);
  if (issue.ok) record.issue = issue.number; else warnings.push("issue:" + issue.status);

  // Persist the request record in the repo.
  const rec = await ghCreateFile(env, `${REQUESTS_DIR}/${id}/request.json`,
    b64encode(JSON.stringify(record, null, 2) + "\n"), `Request ${id}: ${issueTitle}`);
  if (!rec.ok) return json({ error: `Could not save the request (${rec.status}).` }, 502);

  // Email notification (best-effort).
  const mail = await sendEmail(env, `[Policy Library] ${issueTitle}`,
    `<h2>${escapeHtml(heading)}</h2>` +
    `<p><b>Requested by:</b> ${escapeHtml(author)}${email ? " (" + escapeHtml(email) + ")" : ""}</p>` +
    (kind === "new" ? `<p><b>Proposed title:</b> ${escapeHtml(title)}</p>` : `<p><b>Policy:</b> ${escapeHtml(policy || "—")}</p>`) +
    (edition ? `<p><b>Edition:</b> ${escapeHtml(edition)}</p>` : "") +
    (uploadPath ? `<p><b>Attached:</b> ${escapeHtml(uploadPath)}</p>` : "") +
    `<p style="white-space:pre-wrap">${escapeHtml(details)}</p>` +
    (issue.ok ? `<p><a href="${issue.url}">View issue #${issue.number}</a></p>` : ""));
  if (!mail.ok && !mail.skipped) warnings.push("email:" + mail.status);

  return json({ ok: true, id, issue: issue.ok ? issue.number : null, warnings }, 201);
}

// ---- entry point ---------------------------------------------------------

export default {
  async fetch(request, env) {
    const auth = authedUser(request, env);
    if (!auth.configured) {
      return new Response(
        "Access control is not configured yet. Set the AUTH_USER and AUTH_PASS " +
        "secrets on this Worker to enable the login.",
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
    if (!auth.ok) return unauthorized();

    const url = new URL(request.url);
    if (url.pathname === "/api/comments") return handleComments(request, env, auth);
    if (url.pathname === "/api/annotations") return handleAnnotations(request, env, auth);
    if (url.pathname === "/api/requests") return handleRequests(request, env, auth);

    // Authenticated → serve the requested static asset.
    return env.ASSETS.fetch(request);
  },
};
