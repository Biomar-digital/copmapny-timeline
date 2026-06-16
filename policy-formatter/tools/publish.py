#!/usr/bin/env python3
"""
Publish the policy library.

Reads policies/registry.json (the source of truth, edited via Claude Code),
(re)generates each policy's documents as branded PDFs into docs/files/ and
writes the docs/library.json index that the static web page (docs/) reads.

Each policy has one or more `editions` (versions over time). Each edition has
one or more `documents` (downloadable variants shown together on the card, e.g.
the Policy and its Implementation, or English/Spanish editions). A document is
always rendered without the board page ("non-approval"); the board signatures /
approval page ("approval") is only generated when the document sets
`board_approval: true`.

Usage:
    python policy-formatter/tools/publish.py
"""
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PF = os.path.normpath(os.path.join(HERE, ".."))          # policy-formatter/
REPO = os.path.normpath(os.path.join(PF, ".."))          # repo root
SOURCES = os.path.join(REPO, "policies", "sources")
REGISTRY = os.path.join(REPO, "policies", "registry.json")
FILES = os.path.join(REPO, "docs", "files")
LIBRARY = os.path.join(REPO, "docs", "library.json")


def _slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def _gen(source, title, year, date, name_base, tag, extra):
    out = os.path.join(FILES, f"{name_base}_{date}_{tag}.pdf")
    cmd = [sys.executable, os.path.join(PF, "format_policy.py"), source,
           "--title", title, "--year", year, "--date", date, "-o", out] + extra
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{title} [{tag}]: {r.stderr[-400:]}")
    return os.path.relpath(out, os.path.join(REPO, "docs"))


def _editions(p):
    """Editions list (oldest first); falls back to the legacy flat schema."""
    if p.get("editions"):
        return p["editions"]
    return [{
        "version": p.get("version", "Version 1"),
        "date": p.get("date", "2026-06"),
        "approval_date": p.get("approval_date", ""),
        "source": p["source"],
        "notes": p.get("notes", ""),
    }]


def _documents(ed):
    """Documents within an edition; legacy editions get a single document.
    Legacy single-source editions keep the board approval page (board_approval
    defaults to True) so existing policies are unchanged."""
    if ed.get("documents"):
        return ed["documents"]
    return [{
        "label": "Policy",
        "language": None,
        "source": ed["source"],
        "board_approval": ed.get("board_approval", True),
    }]


def main():
    os.makedirs(FILES, exist_ok=True)
    reg = json.load(open(REGISTRY, encoding="utf-8"))
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    out_policies = []

    for p in reg["policies"]:
        eds_out = []
        for ed in _editions(p):
            date = ed["date"]
            year = date.split("-")[0]
            docs_out = []
            for doc in _documents(ed):
                src = os.path.join(SOURCES, doc["source"])
                if not os.path.exists(src):
                    raise FileNotFoundError(src)
                label = doc.get("label", "Policy")
                name_base = f"{_slug(p['title'])}__{_slug(label)}"
                files = {"non_approval": _gen(src, p["title"], year, date, name_base, "non-approval", ["--no-signatures"])}
                if doc.get("board_approval"):
                    extra = ["--owner", p.get("owner", ""),
                             "--approver", p.get("approver", "Executive Committee")]
                    if ed.get("approval_date"):
                        extra += ["--approval-date", ed["approval_date"]]
                    if ed.get("version"):
                        extra += ["--version", ed["version"] + ":"]
                    files["approval"] = _gen(src, p["title"], year, date, name_base, "approval", extra)
                docs_out.append({
                    "label": label,
                    "language": doc.get("language") or p.get("language", "English"),
                    "files": files,
                })
            eds_out.append({
                "version": ed.get("version", "Version 1"),
                "date": date,
                "approval_date": ed.get("approval_date", ""),
                "notes": ed.get("notes", ""),
                "generated_at": today,
                "documents": docs_out,
            })

        out_policies.append({
            "id": p["id"], "title": p["title"],
            "category": p.get("category", "Policy"),
            "language": p.get("language", "English"),
            "owner": p.get("owner", ""), "approver": p.get("approver", ""),
            "editions": eds_out,
        })
        nd = sum(len(e["documents"]) for e in eds_out)
        print(f"  published {p['title']}  ({len(eds_out)} edition(s), {nd} document(s))")

    data = {"brand": "BioMar Group", "updated": today, "policies": out_policies}
    json.dump(data, open(LIBRARY, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    with open(os.path.join(REPO, "docs", "library-data.js"), "w", encoding="utf-8") as f:
        f.write("window.LIBRARY = " + json.dumps(data, ensure_ascii=False) + ";\n")
    print(f"\nwrote {os.path.relpath(LIBRARY, REPO)}  ({len(out_policies)} policies)")


if __name__ == "__main__":
    main()
