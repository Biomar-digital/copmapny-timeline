// Login / request-access page.

const tabs = document.querySelectorAll(".lg-tab");
const forms = { signin: document.getElementById("signinForm"), register: document.getElementById("registerForm") };

tabs.forEach(t => t.addEventListener("click", () => {
  tabs.forEach(x => x.classList.toggle("active", x === t));
  const tab = t.dataset.tab;
  forms.signin.hidden = tab !== "signin";
  forms.register.hidden = tab !== "register";
}));

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
    location.href = "index.html";
  } catch (err) {
    setStatus(status, err.message);
    btn.disabled = false;
  }
});

document.getElementById("registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("rgStatus");
  const btn = e.target.querySelector("button");
  setStatus(status, "Sending…");
  btn.disabled = true;
  try {
    const r = await fetch("api/auth/register", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.getElementById("rgName").value.trim(),
        email: document.getElementById("rgEmail").value.trim(),
        password: document.getElementById("rgPass").value,
      }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    setStatus(status, "Request sent ✓ — an administrator will review it. You'll be able to sign in once approved.", true);
    e.target.reset();
  } catch (err) {
    setStatus(status, err.message);
    btn.disabled = false;
  }
});
