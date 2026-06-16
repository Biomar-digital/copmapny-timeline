#!/usr/bin/env python3
"""
Publish the policy library.

Reads policies/registry.json (the source of truth, edited via Claude Code),
(re)generates each policy as two PDFs - "approval" (board signatures page +
version card) and "non-approval" - into docs/files/, and writes the
docs/library.json index that the static web page (docs/) reads.

Usage:
    python policy-formatter/tools/publish.py

Run from the repository root (or anywhere; paths are resolved relative to the
repo, which is the parent of policy-formatter/).
"""
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PF = os.path.normpath(os.path.join(HERE, ".."))          # policy-formatter/
REPO = os.path.normpath(os.path.join(PF, ".."))          # repo root
SOURCES = os.path.join(REPO, "policies", "sources")
REGISTRY = os.path.join(REPO, "policies", "registry.json")
FILES = os.path.join(REPO, "docs", "files")
LIBRARY = os.path.join(REPO, "docs", "library.json")


def _gen(source, title, year, date, tag, extra):
    slug = "_".join(title.split())
    out = os.path.join(FILES, f"{slug}_{date}_{tag}.pdf")
    cmd = [sys.executable, os.path.join(PF, "format_policy.py"), source,
           "--title", title, "--year", year, "--date", date, "-o", out] + extra
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{title} [{tag}]: {r.stderr[-400:]}")
    return os.path.relpath(out, os.path.join(REPO, "docs"))


def _editions(p):
    """Return the policy's editions list (oldest first). Falls back to the
    legacy flat schema (single edition) when `editions` is absent, so old
    registry files keep working."""
    if p.get("editions"):
        return p["editions"]
    return [{
        "version": p.get("version", "Version 1"),
        "date": p.get("date", "2026-06"),
        "approval_date": p.get("approval_date", ""),
        "source": p["source"],
        "notes": p.get("notes", ""),
    }]


def main():
    os.makedirs(FILES, exist_ok=True)
    reg = json.load(open(REGISTRY, encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    today = now
    out_policies = []

    for p in reg["policies"]:
        eds_out = []
        for ed in _editions(p):
            src = os.path.join(SOURCES, ed["source"])
            if not os.path.exists(src):
                raise FileNotFoundError(src)
            date = ed["date"]
            year = date.split("-")[0]
            # approval set: board signatures page + version card
            approval_extra = ["--owner", p.get("owner", ""),
                              "--approver", p.get("approver", "Executive Committee")]
            if ed.get("approval_date"):
                approval_extra += ["--approval-date", ed["approval_date"]]
            if ed.get("version"):
                approval_extra += ["--version", ed["version"] + ":"]
            f_appr = _gen(src, p["title"], year, date, "approval", approval_extra)
            f_non = _gen(src, p["title"], year, date, "non-approval", ["--no-signatures"])
            eds_out.append({
                "version": ed.get("version", "Version 1"),
                "date": date,
                "approval_date": ed.get("approval_date", ""),
                "notes": ed.get("notes", ""),
                "generated_at": today,
                "files": {"approval": f_appr, "non_approval": f_non},
            })

        out_policies.append({
            "id": p["id"], "title": p["title"], "language": p.get("language", "English"),
            "owner": p.get("owner", ""), "approver": p.get("approver", ""),
            "editions": eds_out,
        })
        n = len(eds_out)
        print(f"  published {p['title']}  ({n} edition{'s' if n != 1 else ''})")

    data = {"brand": "BioMar Group", "updated": today, "policies": out_policies}
    json.dump(data, open(LIBRARY, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    # Also embed the data as JS so the page works when opened directly from disk
    # (file://), where fetch() is blocked - no server or GitHub Pages needed.
    with open(os.path.join(REPO, "docs", "library-data.js"), "w", encoding="utf-8") as f:
        f.write("window.LIBRARY = " + json.dumps(data, ensure_ascii=False) + ";\n")
    print(f"\nwrote {os.path.relpath(LIBRARY, REPO)}  ({len(out_policies)} policies)")


if __name__ == "__main__":
    main()
