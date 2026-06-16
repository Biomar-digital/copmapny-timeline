# Policy requests

Change / new-policy requests submitted by readers from the web library, one
folder per request: `policies/requests/<id>/`.

* `request.json` — the request record (kind, requester, details, status, the
  related policy/edition, the GitHub issue number, and the uploaded file path
  if any).
* `<uploaded-file>` — an optional `.docx`/`.pdf` the requester attached
  (e.g. a draft of the new policy). This is directly usable as a
  `policies/sources/` input when publishing.

Each request also opens a **GitHub issue** (label `policy-request`) and sends an
email notification, so administrators are alerted and can triage. An AI agent
connected to the repo can read these to act on the requests.

`kind` is `"new"` (create a new policy) or `"change"` (edit an existing one).
`status` starts as `"open"`.
