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
  `cover_year` (default OFF — covers carry no year; opt in with `true`),
  `lead_title`, `body_size`, `footer_note`, `version_date`, and on a document
  `board_approval: true` (renders BOTH an approval and a non-approval variant).
- Design-heavy pieces (position statements, Responsible Sourcing) are served as
  the original PDF via `tools/use_original.py`.
- **No board signatures page** (removed globally — board composition changes).
  The two variants differ only by the back-cover card: "with approval
  information" (approval) shows the approver / owner / approval-date card; the
  "without approval information" (non-approval) shows no card.

## Editing & formatting playbook (any agent must be able to do this)

Everything needed lives in the repo — no backend. The loop is: edit the source
→ regenerate → **render to PNG and eyeball** → commit.

- **Pipeline:** `policies/sources/*.docx` → `policy-formatter/model.py`
  (Word → blocks: `Heading`, `Body`, `Bullet`, `TableBlock`, `ImageBlock`,
  `Columns`) → `generator.py` (branded PDF) and `docx_generator.py` (branded,
  editable Word whose cover is page 1 of the PDF, plus logo header + footer).
  `tools/publish.py` reads `registry.json` and regenerates every PDF + `.docx`
  into `docs/files/` and refreshes `docs/library.json`.
- **Regenerate one doc while iterating:** `python policy-formatter/format_policy.py
  <source.docx> --title "…" --no-cover-year --owner "…" --approver "…"
  --approval-date "dd-mm-yyyy" --no-signatures -o /tmp/x.pdf`. Full library:
  `python policy-formatter/tools/publish.py`.
- **Editing sources:** use `python-docx`. Body clauses are one paragraph
  ("3.1 text"); the generator renders a leading clause number in bold. Bullets =
  paragraphs whose style name contains "List" (`List Paragraph`/`List Bullet`).
  **Bullets inside table cells** are preserved (model marks list items, generator
  renders hanging bullets) — so lists in recommendation tables render correctly.
- **Importing an official PDF** (`tools/import_pdf.py`) is a starting point but
  its heuristics DROP content (e.g. it silently lost Articles 3.2 / 11.5 / 11.6).
  ALWAYS verify: extract the original's numbered items and diff against the
  rebuilt source; for regular legal docs a purpose-built parser is safer. Also
  normalise ligatures (ﬁ→fi, ﬂ→fl).
- **Registry `editions`:** each edition has `version`, `date` (YYYY-MM →
  filenames), `approval_date`, `approver`/owner (policy-level), `notes`,
  `requested_by`, `approved_by`, and `documents` (each with `source`,
  `board_approval`). Approver bodies live in the policy `approver` field.
- **Commit hygiene:** `publish.py` rewrites every file (PDF timestamps), so after
  a targeted change restore the untouched churn
  (`for f in $(git diff --name-only docs/files/); do case "$f" in *ThisDoc*) : ;;
  *) git checkout -- "$f";; esac; done`) and commit only the affected files.
- **Change-request variants:** a request carries `variant` = `Signed`,
  `Unsigned`, or `Both` (in `request.json`). `Both` = apply the change to both
  the approval and non-approval variants.

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
  `pending_review` the current edition's `version` stays as-is. On approval, run:
  `python policy-formatter/tools/mint_version.py <policy_id> --summary "..."
  --requested-by "Name" --prev-source-ref <commit-before-the-change>~1`.
  It bumps the **decimal** (Version 2 → 2.1; reserve integer bumps for major
  changes / board re-approval), appends a new edition (today's date + approval
  date + `notes` summary + `requested_by`), and **freezes the previous edition**
  by repointing it at a versioned copy of its pre-change source recovered from
  git (`--prev-source-ref`), so the old version keeps rendering the old content.
  `publish.py` renders a new PDF/Word per edition, so both coexist in the version
  story. Always pass `--prev-source-ref` (or apply edits to a source copy) — if
  the live source was overwritten in place, the previous version cannot be frozen
  from the working tree. Use `--dry-run` first to preview.
