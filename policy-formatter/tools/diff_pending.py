#!/usr/bin/env python3
"""
Compute a "what changed" comparison for a policy while a change request is
still pending_review — before any version has been minted, so the normal
edition-to-edition diff (diff_versions.py, docs/diffs.json) has nothing to
compare against yet.

Renders the policy TWICE: once from a git worktree checked out at the
"before" commit (its own generator.py/docx_generator.py AND its own source
docx — i.e. exactly how the pipeline produced it right before the fix), and
once from the current working tree. This covers both kinds of pending
change: a content edit (source differs, code the same) and a layout/renderer
fix (code differs, source the same) — either way the two renders are the
real before/after, not just a source-text diff that would miss pure-code
fixes entirely.

Diffs the two PDFs the same way diff_versions.py compares two approved
editions, and writes the result into docs/diffs.json under
diffs[policy_id]["pending"], so the dashboard's "Review & approve" flow can
show a real comparison even though no new edition has been minted yet.

Run this once after applying a change and before marking the request
pending_review — same moment self_review.py runs.

Usage:
    python policy-formatter/tools/diff_pending.py <policy_id> [--before <git-ref>]

    --before defaults to the parent of the most recent commit that touched
    either this policy's source document or the PDF/Word generators — pass
    it explicitly when that commit doesn't correspond to this request (e.g.
    a later, unrelated commit touched the same shared generator file).
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PF = os.path.normpath(os.path.join(HERE, ".."))
REPO = os.path.normpath(os.path.join(PF, ".."))
REGISTRY = os.path.join(REPO, "policies", "registry.json")
LIBRARY = os.path.join(REPO, "docs", "library.json")
DIFFS_JSON = os.path.join(REPO, "docs", "diffs.json")

GENERATOR_FILES = [
    "policy-formatter/generator.py",
    "policy-formatter/docx_generator.py",
    "policy-formatter/model.py",
    "policy-formatter/brand.py",
]

sys.path.insert(0, HERE)
from diff_versions import build_pair  # reuse the exact diff/render machinery


def _run(cmd, cwd=REPO):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}: {r.stderr[-800:]}")
    return r.stdout


def _last_commit_touching(relpaths):
    out = _run(["git", "log", "-1", "--format=%H", "--"] + relpaths).strip()
    if not out:
        raise RuntimeError(f"no commit history for {relpaths}")
    return out


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
        meta += ["--version", "Version 1:"]  # frozen label — see publish.py's _gen
    return meta


def _render(format_policy_py, src, p, ed, doc, out_pdf):
    cover_title = p.get("doc_title", p["title"])
    cmd = [sys.executable, format_policy_py, src,
           "--title", cover_title, "--year", ed["date"].split("-")[0], "--date", ed["date"],
           "-o", out_pdf] + _meta_args(p, ed) + ["--no-signatures"]
    if doc.get("board_approval") or p.get("no_version_card"):
        cmd += ["--has-signed"]
    _run(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("policy_id")
    ap.add_argument("--before", default=None,
                     help="git ref for the 'before' state (default: parent of the most "
                          "recent commit touching this policy's source or the generators)")
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

    before_ref = args.before or f"{_last_commit_touching([rel_src] + GENERATOR_FILES)}^"

    lib = json.load(open(LIBRARY, encoding="utf-8"))
    lp = next((x for x in lib["policies"] if x["id"] == args.policy_id), None)
    if not lp:
        raise SystemExit(f"{args.policy_id} not in library.json — run publish.py first")
    cur_pdf = (lp["editions"][-1]["documents"][0].get("files") or {}).get("non_approval")
    if not cur_pdf:
        raise SystemExit(f"{args.policy_id}: no published non_approval PDF")

    wt = tempfile.mkdtemp(prefix="diffpending_wt_")
    old_pdf_rel = os.path.join("files", "cmp", "_pending_src", f"{args.policy_id}.pdf")
    old_pdf_abs = os.path.join(REPO, "docs", old_pdf_rel)
    try:
        # A full worktree at `before_ref` — not just the one source file —
        # so a renderer-only fix (source untouched, generator.py changed)
        # still renders with the OLD code, exactly how it looked before.
        _run(["git", "worktree", "add", "--detach", "-f", wt, before_ref])
        old_src = os.path.join(wt, rel_src)
        if not os.path.exists(old_src):
            raise RuntimeError(f"{rel_src} did not exist at {before_ref}")
        old_pdf_tmp = os.path.join(wt, "old.pdf")
        _render(os.path.join(wt, "policy-formatter", "format_policy.py"), old_src, p, ed, doc, old_pdf_tmp)

        os.makedirs(os.path.dirname(old_pdf_abs), exist_ok=True)
        shutil.copyfile(old_pdf_tmp, old_pdf_abs)

        old_ed = {"version": "Before this request", "documents": [{"files": {"non_approval": old_pdf_rel}}]}
        new_ed = {"version": "Current pending review", "documents": [{"files": {"non_approval": cur_pdf}}]}
        pair = build_pair(args.policy_id, p.get("title", ""), old_ed, new_ed)
        # A layout/renderer-only fix (source text unchanged) reflows nearly
        # every line, so the word-level text diff is mostly wrapping noise,
        # not real content changes — flag it so the dashboard defaults to the
        # page-image view instead of leading with a wall of false "changes".
        with open(old_src, "rb") as f:
            old_source_bytes = f.read()
        with open(os.path.join(REPO, rel_src), "rb") as f:
            cur_source_bytes = f.read()
        pair["source_unchanged"] = old_source_bytes == cur_source_bytes
    finally:
        _run(["git", "worktree", "remove", "--force", wt])
        if os.path.exists(old_pdf_abs):
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
          f"({pair['old']} -> {pair['new']}) [before={before_ref}]")


if __name__ == "__main__":
    main()
