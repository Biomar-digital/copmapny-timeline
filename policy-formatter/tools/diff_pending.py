#!/usr/bin/env python3
"""
Compute a "what changed" comparison for a policy while a change request is
still pending_review — before any version has been minted, so the normal
edition-to-edition diff (diff_versions.py, docs/diffs.json) has nothing to
compare against yet.

Recovers the pre-change source from git (the state right before the commit
that most recently touched it), renders it with the CURRENT
generator/registry settings, and diffs it against the currently-published
PDF the same way diff_versions.py compares two editions. Writes the result
into docs/diffs.json under diffs[policy_id]["pending"], so the dashboard's
"Review & approve" flow can show a real comparison even though no new
edition has been minted yet.

Run this once after applying a change and before marking the request
pending_review — same moment self_review.py runs.

Usage:
    python policy-formatter/tools/diff_pending.py <policy_id> [--before <git-ref>]
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PF = os.path.normpath(os.path.join(HERE, ".."))
REPO = os.path.normpath(os.path.join(PF, ".."))
REGISTRY = os.path.join(REPO, "policies", "registry.json")
LIBRARY = os.path.join(REPO, "docs", "library.json")
DIFFS_JSON = os.path.join(REPO, "docs", "diffs.json")

sys.path.insert(0, HERE)
from diff_versions import build_pair  # reuse the exact diff/render machinery


def _run(cmd):
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}: {r.stderr[-600:]}")
    return r.stdout


def _last_commit_touching(relpath):
    out = _run(["git", "log", "-1", "--format=%H", "--", relpath]).strip()
    if not out:
        raise RuntimeError(f"no commit history for {relpath}")
    return out


def _git_show_bytes(ref, relpath):
    r = subprocess.run(["git", "show", f"{ref}:{relpath}"], cwd=REPO, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git show {ref}:{relpath} failed: {r.stderr[-600:].decode(errors='replace')}")
    return r.stdout


def _meta_args(p, ed):
    meta = ["--owner", p.get("owner", ""), "--approver", p.get("approver", "Executive Committee")]
    date = ed["date"]
    try:
        vd = datetime.datetime.strptime(date, "%Y-%m").strftime("%B %Y")
    except ValueError:
        vd = date
    meta += ["--version-date", vd]
    if not p.get("cover_year"):
        meta += ["--no-cover-year"]
    if p.get("lead_title"):
        meta += ["--lead-title"]
    if p.get("body_size"):
        meta += ["--body-size", str(p["body_size"])]
    if p.get("head_scale"):
        meta += ["--head-scale", str(p["head_scale"])]
    if p.get("hanging_indent"):
        meta += ["--hanging-indent"]
    if p.get("category"):
        meta += ["--category", p["category"]]
    if p.get("footer_note"):
        meta += ["--footer-note", p["footer_note"]]
    if ed.get("approval_date"):
        meta += ["--approval-date", ed["approval_date"]]
    if ed.get("version"):
        meta += ["--version", ed["version"] + ":"]
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("policy_id")
    ap.add_argument("--before", default=None,
                     help="git ref whose content is the 'before' state "
                          "(default: parent of the last commit that touched the source)")
    args = ap.parse_args()

    reg = json.load(open(REGISTRY, encoding="utf-8"))
    p = next((x for x in reg["policies"] if x["id"] == args.policy_id), None)
    if not p:
        raise SystemExit(f"unknown policy {args.policy_id}")
    ed = (p.get("editions") or [{}])[-1]
    doc = (ed.get("documents") or [{"source": ed.get("source")}])[0]
    src_name = doc.get("source")
    if not src_name:
        raise SystemExit(f"{args.policy_id}: no source document on the current edition")
    rel_src = os.path.join("policies", "sources", src_name)

    before_ref = args.before or f"{_last_commit_touching(rel_src)}^"
    old_bytes = _git_show_bytes(before_ref, rel_src)

    lib = json.load(open(LIBRARY, encoding="utf-8"))
    lp = next((x for x in lib["policies"] if x["id"] == args.policy_id), None)
    if not lp:
        raise SystemExit(f"{args.policy_id} not in library.json — run publish.py first")
    cur_pdf = (lp["editions"][-1]["documents"][0].get("files") or {}).get("non_approval")
    if not cur_pdf:
        raise SystemExit(f"{args.policy_id}: no published non_approval PDF")

    with tempfile.TemporaryDirectory() as tmp:
        old_src = os.path.join(tmp, src_name)
        with open(old_src, "wb") as f:
            f.write(old_bytes)
        old_pdf = os.path.join(tmp, "old.pdf")
        cover_title = p.get("doc_title", p["title"])
        cmd = [sys.executable, os.path.join(PF, "format_policy.py"), old_src,
               "--title", cover_title, "--year", ed["date"].split("-")[0], "--date", ed["date"],
               "-o", old_pdf] + _meta_args(p, ed) + ["--no-signatures"]
        if doc.get("board_approval") or p.get("no_version_card"):
            cmd += ["--has-signed"]
        _run(cmd)

        # render_pages()/build_pair() write page PNGs relative to docs/, so the
        # "old" render needs to live under docs/ too.
        old_pdf_rel = os.path.join("files", "cmp", "_pending_src", f"{args.policy_id}.pdf")
        old_pdf_abs = os.path.join(REPO, "docs", old_pdf_rel)
        os.makedirs(os.path.dirname(old_pdf_abs), exist_ok=True)
        with open(old_pdf, "rb") as f, open(old_pdf_abs, "wb") as g:
            g.write(f.read())

        old_ed = {"version": "Before this request", "documents": [{"files": {"non_approval": old_pdf_rel}}]}
        new_ed = {"version": "Current pending review", "documents": [{"files": {"non_approval": cur_pdf}}]}
        try:
            pair = build_pair(args.policy_id, p.get("title", ""), old_ed, new_ed)
        finally:
            # Only the rendered page PNGs (already copied into cmp/<policy>/) are
            # kept for the dashboard — this raw "old" PDF was just scaffolding
            # for build_pair() to open and diff against.
            os.remove(old_pdf_abs)
            try:
                os.rmdir(os.path.dirname(old_pdf_abs))
            except OSError:
                pass  # not empty (another policy's diff running concurrently) — fine

    diffs = json.load(open(DIFFS_JSON, encoding="utf-8")) if os.path.exists(DIFFS_JSON) else {}
    diffs.setdefault(args.policy_id, {})["pending"] = pair
    json.dump(diffs, open(DIFFS_JSON, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    open(DIFFS_JSON, "a").write("\n")
    print(f"{args.policy_id}: pending diff = {pair['changed']} changed lines "
          f"({pair['old']} -> {pair['new']})")


if __name__ == "__main__":
    main()
