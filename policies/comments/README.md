# Policy comments

Reader comments left on the web library, one JSON file per policy:
`policies/comments/<policy-id>.json` (the `<policy-id>` matches the `id` in
`policies/registry.json`).

These files are written automatically by the site's Worker (via the GitHub API)
when someone adds a comment from the **Version history** panel. They are kept in
the repository on purpose: an AI agent (Claude Code / Codex) connected to this
repo can read them to see the feedback left on each policy version.

## Format

```json
[
  {
    "id": "uuid",
    "edition": "Version 1__2026-06",
    "author": "Jane Doe",
    "text": "Please clarify clause 4.2 in the next revision.",
    "created_at": "2026-06-16T08:20:00.000Z"
  }
]
```

* `edition` — `"<version>__<YYYY-MM>"`, identifying which policy edition the
  comment refers to (matches an entry in that policy's `editions` list).
* Newest comments are appended at the end.

Do not hand-edit while the site is live unless you coordinate, to avoid
clobbering concurrent writes; the Worker uses the file SHA to append safely.
