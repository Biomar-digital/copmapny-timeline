# Policy PDF annotations

Text-anchored notes left on a policy PDF from the web library's **Review &
annotate** view, one JSON file per policy:
`policies/annotations/<policy-id>.json` (the `<policy-id>` matches the `id` in
`policies/registry.json`).

Written automatically by the site's Worker (via the GitHub API) when someone
selects text in a PDF and saves a note. Kept in the repo so an AI agent
(Claude Code / Codex) can read the exact quoted passage each note refers to.

## Format

```json
[
  {
    "id": "uuid",
    "file": "files/Tax_Policy_2026-06_approval.pdf",
    "page": 3,
    "quote": "the exact text the reviewer selected",
    "rects": [{ "x": 0.12, "y": 0.34, "w": 0.4, "h": 0.02 }],
    "edition": "Version 1__2026-06",
    "author": "Jane Doe",
    "text": "Please reword this clause.",
    "created_at": "2026-06-16T08:50:00.000Z"
  }
]
```

* `page` — 1-based page number in that PDF.
* `quote` — the selected text (what the note is about).
* `rects` — highlight rectangles, normalised 0–1 relative to the page, used to
  redraw the highlight in the viewer. The `quote` is what matters for the AI.
