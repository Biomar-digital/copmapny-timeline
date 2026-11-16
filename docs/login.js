// Login / request-access page.

const tabs = document.querySelectorAll(".lg-tab");
const forms = {
  signin: document.getElementById("signinForm"),
  register: document.getElementById("registerForm"),
  forgot: document.getElementById("forgotForm"),
};

// Both the top .lg-tab bar and the inline .lg-link buttons ("Forgot
// password?" / "Back to sign in") switch which form is shown; only the top
// bar itself shows an "active" state (the forgot form has no bar entry).
function showTab(tab) {
  tabs.forEach(x => x.classList.toggle("active", x.dataset.tab === tab));
  for (const [name, form] of Object.entries(forms)) form.hidden = name !== tab;
}
document.querySelectorAll("[data-tab]").forEach(el => el.addEventListener("click", () => showTab(el.dataset.tab)));

function setStatus(el, msg, ok) {
  el.textContent = msg;
  el.classList.toggle("ok", !!ok);
}

document.getElementById("signinForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("siStatus");
  const btn = e.target.querySelector("button");
  setStatus(status, "Signing in…");
  btn.disabled = true;
  try {
    const r = await fetch("api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: document.getElementById("siEmail").value.trim(),
        password: document.getElementById("siPass").value,
      }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    setStatus(status, "Welcome — loading…", true);
    location.href = "/";
  } catch (err) {
    setStatus(status, err.message);
    btn.disabled = false;
  }
});

document.getElementById("forgotForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("fgStatus");
  const btn = e.target.querySelector("button[type=submit]");
  setStatus(status, "Sending…");
  btn.disabled = true;
  try {
    const r = await fetch("api/auth/forgot-password", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: document.getElementById("fgEmail").value.trim() }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    setStatus(status, "If that email matches an approved account, a reset link is on its way ✓", true);
    e.target.reset();
  } catch (err) {
    setStatus(status, err.message);
  } finally {
    btn.disabled = false;
  }
});

// Markets picker: the markets, "Global" (group-wide documents) and "Full access".
// Choosing full access greys out the individual markets — it already covers them.
const mList = document.getElementById("rgMarketList");
function mBox(value, label, cls) {
  return `<label class="lg-mbox ${cls || ""}"><input type="checkbox" value="${value}" /> <span>${label}</span></label>`;
}
mList.innerHTML = mBox(window.ALL_MARKETS, "Full access <em>(all markets and Global)</em>", "lg-mall") +
  mBox(window.GLOBAL_MARKET, "Global <em>(group-wide documents)</em>") +
  window.MARKETS.map(m => mBox(m, m)).join("");
function syncAll() {
  const all = mList.querySelector(`input[value="${window.ALL_MARKETS}"]`).checked;
  mList.querySelectorAll("input").forEach(i => { if (i.value !== window.ALL_MARKETS) i.disabled = all; });
}
mList.addEventListener("change", syncAll);
const pickedMarkets = () => {
  const on = [...mList.querySelectorAll("input:checked")].map(i => i.value);
  return on.includes(window.ALL_MARKETS) ? [window.ALL_MARKETS] : on;
};

document.getElementById("registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("rgStatus");
  const btn = e.target.querySelector("button");
  const markets = pickedMarkets();
  if (!markets.length) { setStatus(status, "Choose at least one market."); return; }
  setStatus(status, "Sending…");
  btn.disabled = true;
  try {
    const r = await fetch("api/auth/register", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.getElementById("rgName").value.trim(),
        email: document.getElementById("rgEmail").value.trim(),
        password: document.getElementById("rgPass").value,
        markets,
      }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    setStatus(status, "Request sent ✓ — an administrator will review it. You'll be able to sign in once approved.", true);
    e.target.reset();
    syncAll();
  } catch (err) {
    setStatus(status, err.message);
    btn.disabled = false;
  }
});
