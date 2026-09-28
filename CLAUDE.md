# BioMar Policy Library — working notes

## Norms (always follow)

- **Double-check before sending.** Never push or declare a change done without
  verifying it first — regenerate the affected PDF(s) and visually compare
  against the original (render to PNG with PyMuPDF/`fitz` and actually look at
  the image, don't just check that it rendered). For a text change, diff word-
  for-word against the source; for a from-scratch new-policy rebuild, diff
  against the requester's uploaded file (`policies/requests/<id>/*.docx`) — that
  IS the "original" here, there is no separate `/tmp/refpdfs/` reference set
  (that path doesn't exist in a fresh session; if an old note mentions it,
  ignore it).
- **Self-review before pending_review.** After applying a change, run the
  automatic self-check and only move the request to `pending_review` if it does
  not fail. Write the atomic requirements to
  `policies/requests/<id>/checklist.json` (each: `{id,label,page?,present:[],
  absent:[]}`), then:
  `python policy-formatter/tools/self_review.py --policy <id> --request <id>
  [--versions "Signed + Unsigned"]`. It checks outputs exist, variants match,
  metadata is complete, **all source content is present (catches dropped
  sections)**, no ligatures, plus every checklist assertion — and writes
  `self_review.json`, which is shown to the human reviewer on the Requests page.
  If it reports `fail`, fix and re-run; do not hand off a failing change.

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

## Fresh-session setup

Each session starts in a brand-new sandbox — nothing installed persists from a
previous session.

- **Install deps first**: `pip install -r policy-formatter/requirements.txt`
  (python-docx, reportlab, pillow, pymupdf). `publish.py` fails with
  `ModuleNotFoundError` until this runs.
- **LibreOffice does not work in this sandbox** (fails even on the repo's own
  known-good files — it's an environment issue, not a file issue). Don't rely
  on it to render a requester's raw uploaded `.docx` for a "what does the
  reference look like" check. Instead read the raw XML with `python-docx`
  (styles, `numPr`/`numFmt` for auto-numbered lists, run-level `<w:u>`/`<w:b>`
  for underline/bold) and reason about the structure directly — this is how
  every new-policy rebuild this repo has done was actually verified.
- **The live site is not reachable from this sandbox** (outbound network
  policy blocks it — same for `curl` and `WebFetch`). You cannot self-check
  "is it live" by hitting the URL. Trust the deploy pipeline (see below) and,
  if the user reports something looks wrong, ask them for a screenshot rather
  than trying to fetch it yourself.

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
  a targeted change restore the untouched churn and commit only the affected
  files. **Build an explicit KEEP list and `git add` it FIRST, then revert
  everything still unstaged** — not the other way around:
  ```
  KEEP=(docs/files/ThisDoc.pdf docs/library.json docs/library-data.js policies/registry.json)
  git add "${KEEP[@]}"
  git add policies/sources/ThisDoc.docx   # + any other new/untracked files you touched
  git status --porcelain | grep "^ M" | awk '{print $2}' | xargs -r git checkout --
  ```
  If you instead loop over modified files reverting everything that doesn't
  match a filename pattern (the old approach), it is very easy for the pattern
  to also swallow files you *did* mean to change — e.g. `policy-formatter/generator.py`
  itself, if you fixed a bug in the renderer as part of this change. That has
  actually happened in this repo (twice, same session) — a broad revert loop
  silently discarded a real code fix along with the timestamp churn, and it
  wasn't caught until the very next self-review. `git diff --cached --stat
  policy-formatter/*.py` right after staging is a cheap sanity check before
  committing if you touched the generator.
- **Change-request variants:** a request carries `variant` = `Signed`,
  `Unsigned`, or `Both` (in `request.json`). `Both` = apply the change to both
  the approval and non-approval variants.

## New policy requests (`request.json` `"kind": "new"`)

A recurring request shape: someone uploads an existing Word doc to
`policies/requests/<id>/*.docx` with details like "Document to be updated to
the newest BioMar visual style, but keeping everything else (structure,
content, etc.)." — i.e. restyle into this template, don't touch the content.
`versions` in the request (`"Signed"` / `"Unsigned"` / `"Signed + Unsigned"`)
maps to `board_approval: true/false` on the new registry document.

1. **Inspect before deciding copy-vs-rebuild.** Open the uploaded `.docx` with
   `python-docx` and dump every non-empty paragraph's `(style name, text)`,
   plus `len(d.tables)`/`len(d.inline_shapes)`. This tells you which of three
   situations you're in:
   - **Clean** (proper `Heading 1`/`List Paragraph` styles, no tables, no
     stray fragments) → copy the file straight into `policies/sources/` almost
     as-is. Fastest, lowest risk (Audit Committee Charter, Dividend and Share
     Buyback Policy).
   - **Salvageable but style-broken** (custom/foreign style names that don't
     contain "heading"/"list" so `model.py`'s classifier misses them; a stray
     duplicate title paragraph; tables that are really blank signature boxes)
     → copy the original (never retype by hand — that's what actually risks
     transcription errors) and patch it surgically with `python-docx`: retag
     specific paragraphs' `.style` to the doc's own built-in `"List Paragraph"`
     style (check `for s in d.styles: print(s.name)` — a non-English/custom
     template usually still has a plain "List Paragraph" defined even if the
     bullets in use have a different name), delete the one stray paragraph,
     etc. (Disclosure Committee Charter: Danish "Opstilling - *" list styles;
     Remuneration and Nomination Committee Charter: several "Heading 1"
     paragraphs were actually unstyled body sentences, correctly demoted
     automatically by `model.py`'s existing `_heading_like()` shape check — a
     long sentence tagged "Heading 1" still renders as body, no fix needed
     there — but two of the Charter's real section titles had NO heading tag
     at all and needed to be added).
   - **Genuinely broken** (a paragraph mid-document IS the real content but
     its Word style says something else with no reliable signal, underline
     used for emphasis where this generator only supports bold, physical
     signature blocks) → rebuild block-by-block with a small python-docx
     script (Data Ethics Policy, Non-Audit Services Policy). Even here, dump
     the ENTIRE source text first and read all of it before writing anything —
     do not summarize/paraphrase, transcribe verbatim into `h1()`/`body()`/
     `bullet()` calls.
2. **Word auto-numbered lists are invisible in `paragraph.text`.** If a list
   looks unmarked (no "a.", "1.", "•" in the text) but reads like an
   enumeration, check `'<w:numPr>' in paragraph._p.xml` before assuming it's
   plain prose — Word may be generating the marker from a list definition
   that `python-docx`'s `.text` never exposes. If so, find the format via
   `word/numbering.xml` (`numId` → `abstractNumId` → `<w:lvl ilvl="0">`'s
   `numFmt`/`lvlText`) and reconstruct the literal markers before retagging to
   `List Paragraph` — a dropped-but-referenced enumeration will orphan any
   in-text cross-reference to it (e.g. "cf. section 2.1.1 (a) above"). Each
   distinct list has its own `numId`; group paragraphs by that to find exactly
   where one list ends and the next (restarting at "a"/"1") begins.
3. **This template removes board-signature pages** (see "No board signatures
   page" above) — that applies here too. A source with a physical two-name
   signature line (or a table of blank underscore lines) should have that
   block dropped, keeping only a short attribution sentence if one exists
   ("Approved by the Audit Committee.") — the digital Owner/Approver card
   replaces the rest. Don't invent a sentence that isn't there.
4. **Owner/approver: use what the document itself states, don't guess beyond
   that.** These docs often say who approved it and who owns it in their own
   closing text ("Approved by the Audit Committee", "This policy is owned by
   Group Finance...") — use that. If genuinely unstated, leave `owner`/
   `approval_date` blank rather than inventing a plausible-sounding org unit;
   self-review flags a blank field as `attention` (not `fail`), and that's the
   *correct* outcome for a field the source never specified — don't try to
   force it to a clean pass.
5. **`hanging_indent: true`** if the document has real tab-separated numbered
   clauses ("1.1", "3.1.1", ...) in the article-of-association style; leave it
   off for plain narrative-prose policies with no clause numbering (Data
   Ethics Policy, Non-Audit Services Policy had none).
6. Verify with a word-level diff (`difflib.SequenceMatcher` on whitespace-
   normalised paragraph text) between the original upload and the new
   `policies/sources/*.docx` — every hunk should be something you did on
   purpose (a dropped signature block, an added list marker, a period added
   for a label you turned into a run-in bold); a ratio noticeably below ~0.98
   with unexplained hunks means something got lost.

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

## Branches & deploying

- **The production branch is `claude/confident-curie-gudwtz`.** This is not
  automatically obvious from a session's own "designated branch" instruction
  (a given session may be assigned a *different* branch name) — check
  `wrangler.toml`'s `GH_BRANCH` var to confirm; that's what the live Worker's
  GitHub API calls (reading/writing `pending.json`, annotations, requests)
  actually read from. **`docs/library.json`/the rendered PDFs are only "live"
  once they're on that specific branch** — if your session's designated
  branch is something else, push to *both*: your own branch (to satisfy the
  session's own git requirements) and `claude/confident-curie-gudwtz` (to
  actually go live):
  ```
  git push origin HEAD:claude/confident-curie-gudwtz
  git push origin HEAD:<your-designated-branch>
  ```
  If the two branches have diverged (different unique commits on each), the
  first fix-up is a rebase of your branch onto `confident-curie-gudwtz` — not
  the other way around, since that one is production.
- **Deploys are automatic — do not try to "deploy" manually.** This site is a
  Cloudflare Worker (not Pages; see `wrangler.toml` — `main = "worker/index.js"`,
  a D1 binding, a cron trigger), connected via Cloudflare Workers Builds: every
  push to `claude/confident-curie-gudwtz` triggers a build and — confirmed
  working — an automatic promotion to serve 100% of traffic, usually within a
  couple of minutes. You do not have Cloudflare credentials in this sandbox
  and cannot `wrangler deploy` yourself; you also cannot `curl`/`WebFetch` the
  live URL to check (network policy blocks it). If a change genuinely isn't
  showing up after several minutes, the fix is almost never "run the deploy
  again" — it's more likely the actual content/registry change has a bug (see
  the commit-hygiene note above about a revert loop silently eating a real
  fix), or the user is looking at a stale browser cache / the wrong dashboard
  tab (Policies vs Guidelines are separate tabs, and a policy only shows under
  the tab matching its `category`).
- **`policies/pending.json` gets a near-guaranteed push conflict.** A
  Cloudflare cron runs every 2 minutes and flips `notified: false → true` on
  whatever pending entries it just emailed, committing straight to
  `claude/confident-curie-gudwtz`. If you've added a new entry to the same
  file, your push will very likely need a rebase, and that rebase will very
  likely conflict right inside `pending.json` (its diff and the cron's diff
  touch nearby/adjacent entries). Resolution is mechanical and safe: keep the
  cron's side (`notified: true` on whatever it flipped) and keep your side
  (the new entry you added) — never drop either. After resolving, always
  re-validate: `python3 -c "import json; json.load(open('policies/pending.json'))"`
  before `git add` + `git rebase --continue`.
- **A repository-rename bot may appear on its own branch**
  (`update_worker_name_to_copmapny-timeline`, authored by
  `cloudflare-workers-and-pages[bot]`) that edits `wrangler.toml`'s `name`
  field. Leave it alone / don't merge it into `claude/confident-curie-gudwtz`
  — the Worker's actual configured name (`globa-policies`, matching its live
  `*.workers.dev` URL) must stay what it already is; that bot commit doesn't
  reflect an intentional rename.
