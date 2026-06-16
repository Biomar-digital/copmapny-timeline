// BioMar Policy Library — edge auth gate.
//
// This Worker runs in front of the static assets (docs/) and protects the whole
// site with HTTP Basic Auth (username + password). Credentials are read from the
// AUTH_USER / AUTH_PASS environment variables, which MUST be set as encrypted
// secrets on the Worker (dashboard → Settings → Variables and Secrets, or
// `wrangler secret put`). They are never stored in this repository.
//
// Fail closed: if the secrets are not configured, the site is NOT served, so an
// accidental deploy can never expose the library publicly.

const REALM = "BioMar Policy Library";

function unauthorized() {
  return new Response("Authentication required.", {
    status: 401,
    headers: {
      "WWW-Authenticate": `Basic realm="${REALM}", charset="UTF-8"`,
      "Cache-Control": "no-store",
    },
  });
}

// Length-independent constant-time comparison.
function safeEqual(a, b) {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  // Compare against a fixed-length digest so differing lengths don't short-circuit.
  let diff = ab.length ^ bb.length;
  const len = Math.max(ab.length, bb.length);
  for (let i = 0; i < len; i++) {
    diff |= (ab[i] || 0) ^ (bb[i] || 0);
  }
  return diff === 0;
}

export default {
  async fetch(request, env) {
    const user = env.AUTH_USER;
    const pass = env.AUTH_PASS;

    if (!user || !pass) {
      return new Response(
        "Access control is not configured yet. Set the AUTH_USER and AUTH_PASS " +
        "secrets on this Worker to enable the login.",
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }

    const header = request.headers.get("Authorization") || "";
    const [scheme, encoded] = header.split(" ");
    if (scheme !== "Basic" || !encoded) return unauthorized();

    let decoded;
    try {
      decoded = atob(encoded);
    } catch {
      return unauthorized();
    }
    const sep = decoded.indexOf(":");
    if (sep < 0) return unauthorized();
    const givenUser = decoded.slice(0, sep);
    const givenPass = decoded.slice(sep + 1);

    // Always run both comparisons to avoid leaking which field was wrong.
    const okUser = safeEqual(givenUser, user);
    const okPass = safeEqual(givenPass, pass);
    if (!okUser || !okPass) return unauthorized();

    // Authenticated → serve the requested static asset.
    return env.ASSETS.fetch(request);
  },
};
