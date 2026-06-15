# Deploy the Policy Library to Cloudflare Pages (free)

The site is a static folder (`docs/`) — no build step, no backend. Cloudflare
Pages hosts it for free and can put it behind a real login for free.

## Option A — Connect the GitHub repo (auto-deploy on every push)

1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git**.
2. Authorize GitHub and pick **biomar-digital/copmapny-timeline**.
3. Build settings:
   - **Framework preset:** None
   - **Build command:** *(leave empty)*
   - **Build output directory:** `docs`
   - **Production branch:** the branch you publish from
4. **Save and Deploy.** You get a URL like `https://biomar-policy-library.pages.dev`.

Every `git push` (after `python policy-formatter/tools/publish.py`) redeploys
automatically.

## Option B — Direct upload from the CLI

```
npm install -g wrangler        # once
wrangler login                 # opens your Cloudflare account
npm run deploy                 # uploads docs/ to Cloudflare Pages
```

(`npm run deploy` runs `wrangler pages deploy docs --project-name=biomar-policy-library`.)

## Add a login (free, optional) — Cloudflare Access

1. Cloudflare dashboard → **Zero Trust → Access → Applications → Add → Self-hosted**.
2. Point it at your Pages domain.
3. Add a policy: e.g. **Allow** emails ending in `@biomar.com` (or a specific
   list). Users sign in with an email one-time-code or Google/Microsoft SSO.

Free for up to 50 users. This is proper authentication (server-side), unlike a
client-side password.
