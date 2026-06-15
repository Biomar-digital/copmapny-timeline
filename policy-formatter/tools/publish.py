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


def main():
    os.makedirs(FILES, exist_ok=True)
    reg = json.load(open(REGISTRY, encoding="utf-8"))
    today = datetime.date.today().isoformat()
    out_policies = []

    for p in reg["policies"]:
        src = os.path.join(SOURCES, p["source"])
        if not os.path.exists(src):
            raise FileNotFoundError(src)
        year = p.get("date", "2026-06").split("-")[0]
        date = p["date"]
        # approval set: board signatures page + version card
        approval_extra = ["--owner", p.get("owner", ""),
                          "--approver", p.get("approver", "Executive Committee")]
        if p.get("approval_date"):
            approval_extra += ["--approval-date", p["approval_date"]]
        if p.get("version"):
            approval_extra += ["--version", p["version"] + ":"]
        f_appr = _gen(src, p["title"], year, date, "approval", approval_extra)
        f_non = _gen(src, p["title"], year, date, "non-approval", ["--no-signatures"])

        out_policies.append({
            "id": p["id"], "title": p["title"], "language": p.get("language", "English"),
            "owner": p.get("owner", ""), "approver": p.get("approver", ""),
            "editions": [{
                "version": p.get("version", "Version 1"),
                "date": date,
                "approval_date": p.get("approval_date", ""),
                "generated_at": today,
                "files": {"approval": f_appr, "non_approval": f_non},
            }],
        })
        print(f"  published {p['title']}")

    json.dump({"brand": "BioMar Group", "updated": today, "policies": out_policies},
              open(LIBRARY, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\nwrote {os.path.relpath(LIBRARY, REPO)}  ({len(out_policies)} policies)")


if __name__ == "__main__":
    main()
