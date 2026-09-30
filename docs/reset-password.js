// Reset-password page: reads the one-time token from the URL and sets a new password.

function setStatus(el, msg, ok) {
  el.textContent = msg;
  el.classList.toggle("ok", !!ok);
}

const token = new URLSearchParams(location.search).get("token") || "";

if (!/^[0-9a-f]{64}$/.test(token)) {
  document.getElementById("resetForm").hidden = true;
  document.getElementById("noTokenForm").hidden = false;
} else {
  document.getElementById("resetForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = document.getElementById("rpStatus");
    const btn = e.target.querySelector("button");
    const pass = document.getElementById("rpPass").value;
    const pass2 = document.getElementById("rpPass2").value;
    if (pass !== pass2) { setStatus(status, "Passwords don't match."); return; }
    setStatus(status, "Saving…");
    btn.disabled = true;
    try {
      const r = await fetch("api/auth/reset-password", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password: pass }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
      setStatus(status, "Password updated ✓ — redirecting to sign in…", true);
      setTimeout(() => { location.href = "/login"; }, 1500);
    } catch (err) {
      setStatus(status, err.message);
      btn.disabled = false;
    }
  });
}
