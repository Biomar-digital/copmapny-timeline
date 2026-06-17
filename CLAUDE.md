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
