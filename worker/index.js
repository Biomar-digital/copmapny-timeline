// BioMar Policy Library — Worker: accounts/auth + feedback APIs + asset gate.
//
// Two roles (admin, visitor) with self-service signup and admin approval, backed
// by Cloudflare D1. Authenticated users see the library; admins also get an
// approvals + notifications inbox. Reader feedback (comments, PDF annotations,
// change/new-policy requests with uploads) is committed to the GitHub repo so an
// AI agent can read and act on it, and is mirrored as events for the admin bell.
//
// Environment:
//   DB                      (D1)      — users, sessions, events.
//   AUTH_USER, AUTH_PASS    (secrets) — seed the first admin account.
//   GH_TOKEN                (secret)  — GitHub token: contents:rw + issues:write.
//   RESEND_API_KEY          (secret)  — optional; email notifications.
//   GH_OWNER, GH_REPO, GH_BRANCH, NOTIFY_EMAIL, RESEND_FROM (vars).

const COMMENTS_DIR = "policies/comments";
const ANNOTATIONS_DIR = "policies/annotations";
const REQUESTS_DIR = "policies/requests";
const SIGNATURES_DIR = "policies/signatures";
const MAX_TEXT = 4000;
const MAX_QUOTE = 1000;
const MAX_AUTHOR = 120;
const MAX_RECTS = 80;
const MAX_FILE = 12 * 1024 * 1024;
const SESSION_MS = 30 * 24 * 3600 * 1000;

// ====================================================================== utils

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers },
  });
}

function bytesToHex(b) { return [...b].map(x => x.toString(16).padStart(2, "0")).join(""); }
function hexToBytes(h) {
  const a = new Uint8Array(h.length / 2);
  for (let i = 0; i < a.length; i++) a[i] = parseInt(h.substr(i * 2, 2), 16);
  return a;
}
function randomHex(n) { const b = new Uint8Array(n); crypto.getRandomValues(b); return bytesToHex(b); }

function timingSafeEqualHex(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

async function pbkdf2(password, saltHex) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt: hexToBytes(saltHex), iterations: 100000, hash: "SHA-256" }, key, 256);
  return bytesToHex(new Uint8Array(bits));
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// base64 (UTF-8 text / raw bytes)
function b64encode(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = ""; for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
function b64decode(b64) {
  const bin = atob(b64.replace(/\s/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}
function bytesToB64(bytes) {
  let bin = ""; const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  return btoa(bin);
}

// ==================================================================== cookies

function getCookie(request, name) {
  const c = request.headers.get("Cookie") || "";
  for (const part of c.split(";")) {
    const idx = part.indexOf("=");
    if (idx < 0) continue;
    if (part.slice(0, idx).trim() === name) return decodeURIComponent(part.slice(idx + 1).trim());
  }
  return null;
}
function sessionCookie(token) {
  return `sid=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${Math.floor(SESSION_MS / 1000)}`;
}
function clearCookie() { return "sid=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0"; }

// ======================================================================== D1

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS users (
     id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
     pw_hash TEXT, pw_salt TEXT, role TEXT NOT NULL DEFAULT 'visitor',
     status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS sessions (
     token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS events (
     id TEXT PRIMARY KEY, type TEXT, summary TEXT, ref TEXT, actor TEXT, created_at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS inbox_state (user_id TEXT PRIMARY KEY, last_seen INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS wallet (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, label TEXT, image TEXT NOT NULL, created_at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS pending_change (id TEXT PRIMARY KEY, policy TEXT NOT NULL, request_id TEXT, title TEXT, status TEXT NOT NULL DEFAULT 'change_pending', updated_at INTEGER, created_at INTEGER NOT NULL)`,
];

// Additive migrations for DBs created before a column existed (ignore errors).
const MIGRATIONS = [
  "ALTER TABLE pending_change ADD COLUMN status TEXT NOT NULL DEFAULT 'change_pending'",
  "ALTER TABLE pending_change ADD COLUMN updated_at INTEGER",
];

let schemaPromise = null;
function ensureSchema(env) {
  if (!schemaPromise) {
    schemaPromise = (async () => {
      for (const stmt of SCHEMA) await env.DB.prepare(stmt).run();
      for (const m of MIGRATIONS) { try { await env.DB.prepare(m).run(); } catch { /* column exists */ } }
      if (env.AUTH_USER && env.AUTH_PASS) {
        const admin = await env.DB.prepare("SELECT id FROM users WHERE role='admin' LIMIT 1").first();
        if (!admin) {
          const salt = randomHex(16);
          const hash = await pbkdf2(env.AUTH_PASS, salt);
          await env.DB.prepare(
            "INSERT INTO users (id,email,name,pw_hash,pw_salt,role,status,created_at) VALUES (?,?,?,?,?,?,?,?)")
            .bind(crypto.randomUUID(), String(env.AUTH_USER).toLowerCase(), "Administrator",
              hash, salt, "admin", "approved", Date.now()).run();
        }
      }
    })().catch(e => { schemaPromise = null; throw e; });
  }
  return schemaPromise;
}

async function resolveUser(request, env) {
  const token = getCookie(request, "sid");
  if (!token) return null;
  const row = await env.DB.prepare(
    `SELECT u.id, u.email, u.name, u.role, u.status, s.expires
       FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?`).bind(token).first();
  if (!row) return null;
  if (row.expires < Date.now()) { await env.DB.prepare("DELETE FROM sessions WHERE token=?").bind(token).run(); return null; }
  if (row.status !== "approved") return null;
  return { id: row.id, email: row.email, name: row.name, role: row.role };
}

async function recordEvent(env, type, summary, ref, actor) {
  if (!env.DB) return;
  try {
    await env.DB.prepare("INSERT INTO events (id,type,summary,ref,actor,created_at) VALUES (?,?,?,?,?,?)")
      .bind(crypto.randomUUID(), type, String(summary).slice(0, 300), ref || "", actor || "", Date.now()).run();
  } catch { /* non-fatal */ }
}

// ================================================================ GitHub/email

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
  const r = await fetch(`${contentsUrl(env, path)}?ref=${encodeURIComponent(env.GH_BRANCH)}`, { headers: ghHeaders(env) });
  if (r.status === 404) return { list: [], sha: null };
  if (!r.ok) throw new Error(`GitHub GET ${r.status}`);
  const data = await r.json();
  let list = []; try { list = JSON.parse(b64decode(data.content)); } catch { list = []; }
  if (!Array.isArray(list)) list = [];
  return { list, sha: data.sha };
}
async function ghPutList(env, path, list, sha, message) {
  const body = { message, content: b64encode(JSON.stringify(list, null, 2) + "\n"), branch: env.GH_BRANCH };
  if (sha) body.sha = sha;
  return fetch(contentsUrl(env, path), { method: "PUT", headers: { ...ghHeaders(env), "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
async function appendItem(env, path, item, message) {
  for (let i = 0; i < 3; i++) {
    const { list, sha } = await ghGetList(env, path);
    list.push(item);
    const r = await ghPutList(env, path, list, sha, message);
    if (r.ok) return { ok: true };
    if (r.status === 409 || r.status === 422) continue;
    return { ok: false, status: r.status };
  }
  return { ok: false, status: 409 };
}
async function ghCreateFile(env, path, contentB64, message) {
  return fetch(contentsUrl(env, path), { method: "PUT", headers: { ...ghHeaders(env), "Content-Type": "application/json" }, body: JSON.stringify({ message, content: contentB64, branch: env.GH_BRANCH }) });
}
async function ghCreateIssue(env, title, body, labels) {
  const r = await fetch(`https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/issues`,
    { method: "POST", headers: { ...ghHeaders(env), "Content-Type": "application/json" }, body: JSON.stringify({ title, body, labels }) });
  if (!r.ok) return { ok: false, status: r.status };
  const d = await r.json();
  return { ok: true, number: d.number, url: d.html_url };
}
async function sendEmail(env, subject, html) {
  if (!env.RESEND_API_KEY || !env.NOTIFY_EMAIL) return { ok: false, skipped: true };
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { "Authorization": `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: env.RESEND_FROM || "BioMar Policies <onboarding@resend.dev>", to: [env.NOTIFY_EMAIL], subject, html }),
  });
  return { ok: r.ok, status: r.status };
}

function missingEnv(env) { return ["GH_TOKEN", "GH_OWNER", "GH_REPO", "GH_BRANCH"].filter(k => !env[k]); }
function safePolicyId(id) { return typeof id === "string" && /^[a-z0-9-]{1,80}$/.test(id) ? id : null; }
function safeFile(f) { return typeof f === "string" && /^files\/[A-Za-z0-9._-]+\.pdf$/.test(f) ? f : null; }
function safeUploadName(name) {
  const base = String(name || "upload").split(/[\\/]/).pop().slice(-120).replace(/[^A-Za-z0-9._-]/g, "_");
  return /\.(docx|pdf)$/i.test(base) ? base : null;
}
function parseDataUrl(s) {
  const m = /^data:(image\/(png|jpeg));base64,([A-Za-z0-9+/=]+)$/.exec(String(s || ""));
  return m ? { ext: m[2] === "jpeg" ? "jpg" : "png", b64: m[3] } : null;
}
function clamp01(n) { n = Number(n); return isFinite(n) ? Math.max(0, Math.min(1, n)) : 0; }
function cleanRects(input) {
  if (!Array.isArray(input)) return [];
  return input.slice(0, MAX_RECTS).map(r => ({ x: clamp01(r.x), y: clamp01(r.y), w: clamp01(r.w), h: clamp01(r.h) }));
}

// ================================================================= auth routes

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

async function handleAuth(request, env, path) {
  if (!env.DB) return json({ error: "Accounts not available." }, 503);

  if (path === "/api/auth/me" && request.method === "GET") {
    const user = await resolveUser(request, env);
    return json({ user: user ? { name: user.name, email: user.email, role: user.role } : null });
  }

  if (path === "/api/auth/register" && request.method === "POST") {
    let p; try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    const email = String(p.email || "").trim().toLowerCase().slice(0, 200);
    const name = String(p.name || "").trim().slice(0, MAX_AUTHOR);
    const password = String(p.password || "");
    if (!EMAIL_RE.test(email)) return json({ error: "Enter a valid email." }, 400);
    if (!name) return json({ error: "Enter your name." }, 400);
    if (password.length < 8) return json({ error: "Password must be at least 8 characters." }, 400);
    const exists = await env.DB.prepare("SELECT id FROM users WHERE email=?").bind(email).first();
    if (exists) return json({ error: "An account with that email already exists." }, 409);
    const salt = randomHex(16);
    const hash = await pbkdf2(password, salt);
    await env.DB.prepare("INSERT INTO users (id,email,name,pw_hash,pw_salt,role,status,created_at) VALUES (?,?,?,?,?,?,?,?)")
      .bind(crypto.randomUUID(), email, name, hash, salt, "visitor", "pending", Date.now()).run();
    await recordEvent(env, "account_request", `${name} requested an account`, email, name);
    return json({ ok: true, pending: true });
  }

  if (path === "/api/auth/login" && request.method === "POST") {
    let p; try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    const email = String(p.email || "").trim().toLowerCase().slice(0, 200);
    const password = String(p.password || "");
    const u = await env.DB.prepare("SELECT * FROM users WHERE email=?").bind(email).first();
    if (!u || !u.pw_hash) return json({ error: "Invalid email or password." }, 401);
    const hash = await pbkdf2(password, u.pw_salt);
    if (!timingSafeEqualHex(hash, u.pw_hash)) return json({ error: "Invalid email or password." }, 401);
    if (u.status === "pending") return json({ error: "Your account is awaiting approval." }, 403);
    if (u.status !== "approved") return json({ error: "This account is not active." }, 403);
    const token = randomHex(32);
    await env.DB.prepare("INSERT INTO sessions (token,user_id,expires) VALUES (?,?,?)")
      .bind(token, u.id, Date.now() + SESSION_MS).run();
    return json({ ok: true, user: { name: u.name, email: u.email, role: u.role } }, 200, { "Set-Cookie": sessionCookie(token) });
  }

  if (path === "/api/auth/logout" && request.method === "POST") {
    const token = getCookie(request, "sid");
    if (token) await env.DB.prepare("DELETE FROM sessions WHERE token=?").bind(token).run();
    return json({ ok: true }, 200, { "Set-Cookie": clearCookie() });
  }

  return json({ error: "Not found." }, 404);
}

// ================================================================ admin routes

async function handleAdmin(request, env, path, user) {
  if (path === "/api/admin/users" && request.method === "GET") {
    const status = new URL(request.url).searchParams.get("status");
    const q = status
      ? env.DB.prepare("SELECT id,email,name,role,status,created_at FROM users WHERE status=? ORDER BY created_at DESC").bind(status)
      : env.DB.prepare("SELECT id,email,name,role,status,created_at FROM users ORDER BY created_at DESC");
    const { results } = await q.all();
    return json({ users: results || [] });
  }

  if ((path === "/api/admin/users/approve" || path === "/api/admin/users/reject") && request.method === "POST") {
    let p; try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    const id = String(p.id || "");
    const status = path.endsWith("approve") ? "approved" : "rejected";
    const u = await env.DB.prepare("SELECT name,email FROM users WHERE id=?").bind(id).first();
    if (!u) return json({ error: "User not found." }, 404);
    await env.DB.prepare("UPDATE users SET status=? WHERE id=?").bind(status, id).run();
    await recordEvent(env, "account_" + status, `${u.name} ${status}`, u.email, user.name);
    return json({ ok: true });
  }

  if (path === "/api/admin/inbox" && request.method === "GET") {
    const seen = await env.DB.prepare("SELECT last_seen FROM inbox_state WHERE user_id=?").bind(user.id).first();
    const lastSeen = seen ? seen.last_seen : 0;
    const { results } = await env.DB.prepare(
      "SELECT type,summary,ref,actor,created_at FROM events ORDER BY created_at DESC LIMIT 50").all();
    const unread = (results || []).filter(e => e.created_at > lastSeen).length;
    return json({ events: results || [], unread });
  }

  if (path === "/api/admin/inbox/seen" && request.method === "POST") {
    await env.DB.prepare(
      "INSERT INTO inbox_state (user_id,last_seen) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET last_seen=excluded.last_seen")
      .bind(user.id, Date.now()).run();
    return json({ ok: true });
  }

  return json({ error: "Not found." }, 404);
}

// ============================================================== feedback routes

async function handleComments(request, env, user) {
  const miss = missingEnv(env); if (miss.length) return json({ error: "Comments backend not configured. Missing: " + miss.join(", ") }, 503);
  const url = new URL(request.url);
  if (request.method === "GET") {
    const id = safePolicyId(url.searchParams.get("policy"));
    if (!id) return json({ error: "Invalid policy id." }, 400);
    const { list } = await ghGetList(env, `${COMMENTS_DIR}/${id}.json`);
    return json({ comments: list });
  }
  if (request.method === "POST") {
    let p; try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    const id = safePolicyId(p.policy); if (!id) return json({ error: "Invalid policy id." }, 400);
    const edition = String(p.edition || "").slice(0, 200);
    const text = String(p.text || "").trim().slice(0, MAX_TEXT);
    const author = String(p.author || user.name || "Anonymous").trim().slice(0, MAX_AUTHOR) || "Anonymous";
    if (!edition) return json({ error: "Missing edition." }, 400);
    if (!text) return json({ error: "Comment text is required." }, 400);
    const comment = { id: crypto.randomUUID(), edition, author, text, created_at: new Date().toISOString() };
    const res = await appendItem(env, `${COMMENTS_DIR}/${id}.json`, comment, `Add comment on ${id} (${edition})`);
    if (!res.ok) return json({ error: `GitHub write failed (${res.status}).` }, 502);
    await recordEvent(env, "comment", `${author} commented on ${id}`, id, author);
    return json({ comment }, 201);
  }
  return json({ error: "Method not allowed." }, 405);
}

async function handleAnnotations(request, env, user) {
  const miss = missingEnv(env); if (miss.length) return json({ error: "Annotations backend not configured. Missing: " + miss.join(", ") }, 503);
  const url = new URL(request.url);
  if (request.method === "GET") {
    const id = safePolicyId(url.searchParams.get("policy"));
    if (!id) return json({ error: "Invalid policy id." }, 400);
    const { list } = await ghGetList(env, `${ANNOTATIONS_DIR}/${id}.json`);
    const file = url.searchParams.get("file");
    return json({ annotations: file ? list.filter(a => a.file === file) : list });
  }
  if (request.method === "POST") {
    let p; try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    const id = safePolicyId(p.policy); if (!id) return json({ error: "Invalid policy id." }, 400);
    const file = safeFile(p.file); if (!file) return json({ error: "Invalid file." }, 400);
    const page = parseInt(p.page, 10); if (!(page >= 1 && page <= 5000)) return json({ error: "Invalid page." }, 400);
    const quote = String(p.quote || "").trim().slice(0, MAX_QUOTE);
    const text = String(p.text || "").trim().slice(0, MAX_TEXT);
    const author = String(p.author || user.name || "Anonymous").trim().slice(0, MAX_AUTHOR) || "Anonymous";
    if (!text) return json({ error: "Comment text is required." }, 400);
    const ann = { id: crypto.randomUUID(), file, page, quote, rects: cleanRects(p.rects), edition: String(p.edition || "").slice(0, 200), author, text, created_at: new Date().toISOString() };
    const res = await appendItem(env, `${ANNOTATIONS_DIR}/${id}.json`, ann, `Add annotation on ${id} (${file} p.${page})`);
    if (!res.ok) return json({ error: `GitHub write failed (${res.status}).` }, 502);
    await recordEvent(env, "annotation", `${author} annotated ${id} (p.${page})`, id, author);
    return json({ annotation: ann }, 201);
  }
  return json({ error: "Method not allowed." }, 405);
}

async function handleRequests(request, env, user) {
  const miss = missingEnv(env); if (miss.length) return json({ error: "Requests backend not configured. Missing: " + miss.join(", ") }, 503);
  if (request.method !== "POST") return json({ error: "Method not allowed." }, 405);
  let form; try { form = await request.formData(); } catch { return json({ error: "Invalid form data." }, 400); }

  const kind = form.get("kind") === "new" ? "new" : "change";
  const author = String(form.get("author") || user.name || "").trim().slice(0, MAX_AUTHOR);
  const email = String(form.get("email") || user.email || "").trim().slice(0, 200);
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

  const record = { id, kind, status: "open", title: kind === "new" ? title : (policy || title), policy, edition, author, email, details, upload: uploadPath, created_at: new Date().toISOString() };
  const heading = kind === "new" ? "New policy request" : "Policy change request";
  const issueTitle = kind === "new" ? `New policy: ${title}` : `Change: ${policy || title}`;
  const issueBody =
    `**${heading}**\n\n- **Requested by:** ${author}${email ? ` (${email})` : ""}\n` +
    (kind === "new" ? `- **Proposed title:** ${title}\n` : `- **Policy:** ${policy || "—"}\n`) +
    (edition ? `- **Edition:** ${edition}\n` : "") +
    (uploadPath ? `- **Attached document:** \`${uploadPath}\`\n` : "") +
    `- **Request record:** \`${REQUESTS_DIR}/${id}/request.json\`\n\n---\n\n${details}\n`;
  const issue = await ghCreateIssue(env, issueTitle, issueBody, ["policy-request", kind === "new" ? "new-policy" : "change-request"]);
  if (issue.ok) record.issue = issue.number; else warnings.push("issue:" + issue.status);

  const rec = await ghCreateFile(env, `${REQUESTS_DIR}/${id}/request.json`, b64encode(JSON.stringify(record, null, 2) + "\n"), `Request ${id}: ${issueTitle}`);
  if (!rec.ok) return json({ error: `Could not save the request (${rec.status}).` }, 502);

  const mail = await sendEmail(env, `[Policy Library] ${issueTitle}`,
    `<h2>${escapeHtml(heading)}</h2><p><b>Requested by:</b> ${escapeHtml(author)}${email ? " (" + escapeHtml(email) + ")" : ""}</p>` +
    (kind === "new" ? `<p><b>Proposed title:</b> ${escapeHtml(title)}</p>` : `<p><b>Policy:</b> ${escapeHtml(policy || "—")}</p>`) +
    (uploadPath ? `<p><b>Attached:</b> ${escapeHtml(uploadPath)}</p>` : "") +
    `<p style="white-space:pre-wrap">${escapeHtml(details)}</p>` +
    (issue.ok ? `<p><a href="${issue.url}">View issue #${issue.number}</a></p>` : ""));
  if (!mail.ok && !mail.skipped) warnings.push("email:" + mail.status);

  await recordEvent(env, kind === "new" ? "request_new" : "request_change", `${author}: ${issueTitle}`, policy || "", author);
  if (kind === "change" && policy && env.DB) {
    try {
      await env.DB.prepare("INSERT INTO pending_change (id,policy,request_id,title,created_at) VALUES (?,?,?,?,?)")
        .bind(crypto.randomUUID(), policy, id, issueTitle, Date.now()).run();
    } catch { /* non-fatal */ }
  }
  return json({ ok: true, id, issue: issue.ok ? issue.number : null, warnings }, 201);
}

// ============================================================ /api/signatures

async function handleSignatures(request, env, user) {
  const miss = missingEnv(env); if (miss.length) return json({ error: "Signatures backend not configured. Missing: " + miss.join(", ") }, 503);
  const url = new URL(request.url);
  if (request.method === "GET") {
    const id = safePolicyId(url.searchParams.get("policy"));
    if (!id) return json({ error: "Invalid policy id." }, 400);
    const { list } = await ghGetList(env, `${SIGNATURES_DIR}/${id}.json`);
    return json({ signatures: list });
  }
  if (request.method === "POST") {
    let p; try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    const id = safePolicyId(p.policy); if (!id) return json({ error: "Invalid policy id." }, 400);
    const edition = String(p.edition || "").slice(0, 200);
    const label = String(p.label || "").trim().slice(0, 200);
    if (!label) return json({ error: "Add the name / title for this signature line." }, 400);

    // Image comes either from a saved wallet signature (reuse) or a new upload.
    let b64, ext;
    if (p.walletId) {
      const w = await env.DB.prepare("SELECT image FROM wallet WHERE id=? AND user_id=?").bind(String(p.walletId), user.id).first();
      const parsed = w ? parseDataUrl(w.image) : null;
      if (!parsed) return json({ error: "Saved signature not found." }, 400);
      b64 = parsed.b64; ext = parsed.ext;
    } else {
      const img = parseDataUrl(p.image);
      if (!img) return json({ error: "A signature image is required." }, 400);
      if (img.b64.length > 3500000) return json({ error: "Signature image too large." }, 400);
      b64 = img.b64; ext = img.ext;
      // Save new signatures to the user's wallet so they can reuse them.
      try {
        await env.DB.prepare("INSERT INTO wallet (id,user_id,label,image,created_at) VALUES (?,?,?,?,?)")
          .bind(crypto.randomUUID(), user.id, label, p.image, Date.now()).run();
      } catch { /* non-fatal */ }
    }
    const sigId = crypto.randomUUID();
    const imgPath = `${SIGNATURES_DIR}/${id}/${sigId}.${ext}`;
    const cr = await ghCreateFile(env, imgPath, b64, `Signature on ${id} by ${user.email}`);
    if (!cr.ok) return json({ error: `Could not store signature (${cr.status}).` }, 502);
    // Identity (account) is taken from the session; `label` is the name/title to
    // print on the PDF signature line.
    const sig = { id: sigId, edition, label, name: user.name, account: user.email, image: imgPath, signed_at: new Date().toISOString() };
    const res = await appendItem(env, `${SIGNATURES_DIR}/${id}.json`, sig, `Add signature on ${id} by ${user.email}`);
    if (!res.ok) return json({ error: `Could not record signature (${res.status}).` }, 502);
    await recordEvent(env, "signature", `${user.name} signed ${id}`, id, user.name);
    return json({ signature: sig }, 201);
  }
  return json({ error: "Method not allowed." }, 405);
}

// ============================================================ /api/wallet

async function handleWallet(request, env, user) {
  if (request.method === "GET") {
    const { results } = await env.DB.prepare(
      "SELECT id,label,image,created_at FROM wallet WHERE user_id=? ORDER BY created_at DESC LIMIT 24").bind(user.id).all();
    return json({ signatures: results || [] });
  }
  if (request.method === "DELETE") {
    let p; try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    await env.DB.prepare("DELETE FROM wallet WHERE id=? AND user_id=?").bind(String(p.id || ""), user.id).run();
    return json({ ok: true });
  }
  return json({ error: "Method not allowed." }, 405);
}

// ========================================================= /api/pending

async function handlePending(request, env, user) {
  if (request.method === "GET") {
    // Effective status per policy: 'change_pending' wins over 'pending_review'.
    const { results } = await env.DB.prepare(
      `SELECT policy,
              CASE WHEN SUM(status='change_pending')>0 THEN 'change_pending'
                   ELSE 'pending_review' END AS status,
              COUNT(*) AS n
         FROM pending_change GROUP BY policy`).all();
    return json({ pending: results || [] });
  }
  // Status transitions. 'review' (changes done -> awaiting the requester's
  // review) is admin-only; 'approve' (accept) and 'reopen' (ask for another
  // round) close or re-open the request.
  if (request.method === "POST") {
    let p; try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    const policy = safePolicyId(p.policy);
    const action = String(p.action || "");
    if (!policy) return json({ error: "Invalid policy." }, 400);
    if (action === "review") {
      if (user.role !== "admin") return json({ error: "Forbidden." }, 403);
      await env.DB.prepare("UPDATE pending_change SET status='pending_review', updated_at=? WHERE policy=?")
        .bind(Date.now(), policy).run();
      await recordEvent(env, "change_review", `${user.name}: changes ready for review on ${policy}`, policy, user.name);
    } else if (action === "reopen") {
      await env.DB.prepare("UPDATE pending_change SET status='change_pending', updated_at=? WHERE policy=?")
        .bind(Date.now(), policy).run();
      await recordEvent(env, "change_reopen", `${user.name}: requested another round on ${policy}`, policy, user.name);
    } else if (action === "approve") {
      await env.DB.prepare("DELETE FROM pending_change WHERE policy=?").bind(policy).run();
      await recordEvent(env, "change_approved", `${user.name}: approved changes on ${policy}`, policy, user.name);
    } else {
      return json({ error: "Unknown action." }, 400);
    }
    return json({ ok: true });
  }
  if (request.method === "DELETE") {                 // legacy "mark resolved"
    if (user.role !== "admin") return json({ error: "Forbidden." }, 403);
    let p; try { p = await request.json(); } catch { return json({ error: "Invalid JSON." }, 400); }
    const policy = safePolicyId(p.policy);
    if (!policy) return json({ error: "Invalid policy." }, 400);
    await env.DB.prepare("DELETE FROM pending_change WHERE policy=?").bind(policy).run();
    return json({ ok: true });
  }
  return json({ error: "Method not allowed." }, 405);
}

// ==================================================================== gate

const PUBLIC_ASSETS = new Set(["/login", "/login.html", "/login.js", "/login.css", "/styles.css", "/favicon.png", "/favicon.ico"]);
function isPublicAsset(path) { return PUBLIC_ASSETS.has(path) || path.startsWith("/assets/"); }

// Serve a static asset, but force revalidation of HTML/JS/CSS so a deploy is
// picked up immediately (avoids stale app.js after updates).
async function serveAsset(request, env) {
  const res = await env.ASSETS.fetch(request);
  const path = new URL(request.url).pathname;
  if (path === "/" || path === "/login" || /\.(html|js|css)$/.test(path)) {
    const h = new Headers(res.headers);
    h.set("Cache-Control", "no-cache, must-revalidate");
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
  }
  return res;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (!env.DB) return new Response("Accounts database not configured.", { status: 503 });
    try { await ensureSchema(env); } catch { return new Response("Account store unavailable.", { status: 503 }); }

    // public auth endpoints
    if (path.startsWith("/api/auth/")) return handleAuth(request, env, path);

    const user = await resolveUser(request, env);

    if (path.startsWith("/api/admin/")) {
      if (!user || user.role !== "admin") return json({ error: "Forbidden." }, 403);
      return handleAdmin(request, env, path, user);
    }
    if (path.startsWith("/api/")) {
      if (!user) return json({ error: "Not authenticated." }, 401);
      if (path === "/api/comments") return handleComments(request, env, user);
      if (path === "/api/annotations") return handleAnnotations(request, env, user);
      if (path === "/api/signatures") return handleSignatures(request, env, user);
      if (path === "/api/requests") return handleRequests(request, env, user);
      if (path === "/api/wallet") return handleWallet(request, env, user);
      if (path === "/api/pending") return handlePending(request, env, user);
      return json({ error: "Not found." }, 404);
    }

    if (isPublicAsset(path)) return serveAsset(request, env);

    if (!user) {
      if (request.method === "GET") return Response.redirect(new URL("/login", request.url).toString(), 302);
      return json({ error: "Not authenticated." }, 401);
    }
    return serveAsset(request, env);
  },
};
