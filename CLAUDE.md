# BioMar Policy Library — working notes

## Norms (always follow)

- **Double-check before sending.** Never push or declare a change done without
  verifying it first — regenerate the affected PDF(s) and visually compare
  against the original (render to PNG and look), or check the data, then commit.
  Re-rendered documents must be compared page-by-page to the official PDF in
  `/tmp/refpdfs/` before being considered correct.

## Layout / fidelity reference

- Originals to compare against live in `/tmp/refpdfs/`.
- Re-render pipeline: `policies/registry.json` → `policy-formatter/tools/publish.py`
  → `docs/files/*.pdf` + `docs/library.json`.
- Per-policy switches in `registry.json`: `pdf` (serve the original verbatim),
  `cover_year`, `lead_title`, `body_size`, `footer_note`, `version_date`.
- Design-heavy pieces (position statements, Responsible Sourcing) are served as
  the original PDF via `tools/use_original.py`.
- Unsigned variants: no "Version history / Approval date"; show only the
  Owner / Approver card. Signed variants get the full version card + board page.

## Review workflow

- Change requests, annotations, comments, uploads and signatures are committed
  to the repo under `policies/{requests,annotations,comments,signatures}/` so the
  AI can read them. Dashboard status: change_pending → pending_review → approved.
- Status lives in `policies/pending.json`. When the change is applied, set the
  entry to `pending_review`; a Cloudflare cron (`worker/index.js` `scheduled`,
  every 2 min) emails the requester from Cloudflare (whose egress IS authorised
  in Brevo — CI runners are not) and flags `notified`. Never send these from CI.
- **Annotations/comments are never deleted.** They carry an `edition` field and
  stay tied to the version they were made on, so each version keeps its own
  comments and highlights (shown per-version in the dashboard History modal). A
  later round can look "contradictory" only because older rounds' marks are still
  on file — disambiguate by `created_at` and by request `id`, do not delete.
- Rounds: identify which marks belong to the open request by date/request, apply
  only those, and verify the rest are already reflected in the current PDF.

## Versioning / version story

- Each policy keeps an `editions` list in `registry.json` (oldest first; last =
  current). The version story (dashboard History modal + `library.json`) renders
  every edition with its `version`, `notes` (summary of what changed) and
  `requested_by` (who asked for it).
- **Mint a new version at approval, not on apply.** While a change is in
  `pending_review` the current edition's `version` stays as-is. When you approve,
  append a NEW edition: bump the **decimal** (Version 2 → 2.1; reserve integer
  bumps for major changes / board re-approval), set `date`, leave `approval_date`
  until signed, and fill `notes` (the change summary) + `requested_by`. Keep the
  prior edition and its PDF — `publish.py` renders a new PDF per edition, so the
  old one is preserved automatically. Then re-run `publish.py` and commit.
