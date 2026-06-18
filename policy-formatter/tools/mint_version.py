#!/usr/bin/env python3
"""
Mint a new policy version at approval time (decimal bump, prior version kept).

Run this when a change request is APPROVED. It:
  - finds the policy's current (last) edition E (version Vn, source S);
  - freezes E as the *previous* version by repointing it at a frozen copy of its
    pre-change source (so it always renders the old content), taken from git via
    --prev-source-ref (e.g. the commit before the change was applied);
  - appends a NEW edition (Vn.1 by default) whose source is the current working
    source S (the approved content), dated today, with `notes` (the change
    summary) and `requested_by`, and today's approval date;
  - rebuilds the library (unless --no-build).

The previous edition keeps its own version/date/files; publish.py renders a new
PDF/Word per edition, so both versions coexist in the version story.

Usage:
  python tools/mint_version.py human-rights-policy \
      --summary "p.5 Modern Slavery: 'Australia and UK' -> 'Only UK and AUS'" \
      --requested-by "Jeppe Andersen" \
      --prev-source-ref 70cd611~1
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PF = os.path.normpath(os.path.join(HERE, ".."))
REPO = os.path.normpath(os.path.join(PF, ".."))
REGISTRY = os.path.join(REPO, "policies", "registry.json")
SOURCES = os.path.join(REPO, "policies", "sources")


def bump_decimal(version: str) -> str:
    """'Version 2' -> 'Version 2.1'; 'Version 2.1' -> 'Version 2.2'."""
    m = re.search(r"(\d+)(?:\.(\d+))?", version or "")
    if not m:
        return (version or "Version 1") + ".1"
    major = m.group(1)
    minor = int(m.group(2) or 0) + 1
    return version[:m.start()] + f"{major}.{minor}" + version[m.end():]


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mint an approved policy version (decimal bump).")
    ap.add_argument("policy_id")
    ap.add_argument("--summary", required=True, help="Short changelog for the new version")
    ap.add_argument("--requested-by", dest="requested_by", required=True, help="Who requested the change")
    ap.add_argument("--approved-by", dest="approved_by", default="", help="Who approved the change")
    ap.add_argument("--version", help="Explicit new version label (default: decimal bump)")
    ap.add_argument("--approval-date", dest="approval_date",
                    default=datetime.date.today().strftime("%d-%m-%Y"))
    ap.add_argument("--prev-source-ref", dest="prev_ref",
                    help="git ref to recover the previous version's pristine source "
                         "(e.g. <commit>~1). If omitted, the current source is reused "
                         "for the frozen copy (only correct if edits went to a copy).")
    ap.add_argument("--no-build", action="store_true", help="Skip the publish.py rebuild")
    ap.add_argument("--dry-run", action="store_true", help="Print the change, write nothing")
    args = ap.parse_args(argv)

    reg = json.load(open(REGISTRY, encoding="utf-8"))
    policies = reg["policies"] if isinstance(reg, dict) else reg
    pol = next((p for p in policies if p.get("id") == args.policy_id), None)
    if not pol:
        ap.error(f"policy not found: {args.policy_id}")
    eds = pol.get("editions") or []
    if not eds:
        ap.error("policy has no editions")
    cur = eds[-1]
    new_ver = args.version or bump_decimal(cur.get("version", "Version 1"))

    # The new edition's documents reuse the current sources (approved content).
    docs = cur.get("documents") or [{"label": "Policy", "source": cur.get("source"),
                                     "board_approval": cur.get("board_approval", False)}]

    # Freeze the previous edition: each of its sources becomes a versioned copy so
    # it keeps rendering the pre-change content.
    frozen_docs = []
    for d in docs:
        src = d.get("source")
        if not src:
            frozen_docs.append(dict(d)); continue
        stem, ext = os.path.splitext(src)
        frozen_name = f"{stem}__{slug(cur.get('version','v'))}{ext}"
        frozen_abs = os.path.join(SOURCES, frozen_name)
        if not args.dry_run:
            if args.prev_ref:
                blob = subprocess.run(
                    ["git", "-C", REPO, "show", f"{args.prev_ref}:policies/sources/{src}"],
                    capture_output=True)
                if blob.returncode != 0:
                    ap.error(f"could not read {src} at {args.prev_ref}: {blob.stderr.decode()[:200]}")
                open(frozen_abs, "wb").write(blob.stdout)
            else:
                shutil.copyfile(os.path.join(SOURCES, src), frozen_abs)
        fd = dict(d); fd["source"] = frozen_name
        frozen_docs.append(fd)

    cur["documents"] = frozen_docs
    cur.pop("source", None)  # normalise to documents form

    new_ed = {
        "version": new_ver,
        "date": datetime.date.today().strftime("%Y-%m"),
        "approval_date": args.approval_date,
        "notes": args.summary,
        "requested_by": args.requested_by,
        "approved_by": args.approved_by or args.requested_by,
        "documents": [dict(d) for d in docs],
    }
    eds.append(new_ed)

    print(f"Policy: {pol['title']}")
    print(f"  previous edition frozen as: {cur.get('version')} "
          f"(sources -> {[d.get('source') for d in frozen_docs]})")
    print(f"  new edition: {new_ver}  date {new_ed['date']}  approved {args.approval_date}")
    print(f"  notes: {args.summary}")
    print(f"  requested_by: {args.requested_by}")
    if args.dry_run:
        print("\n[dry-run] registry not written, nothing built.")
        return 0

    json.dump(reg, open(REGISTRY, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    open(REGISTRY, "a").write("\n")
    print(f"\nwrote {os.path.relpath(REGISTRY, REPO)}")

    if not args.no_build:
        r = subprocess.run([sys.executable, os.path.join(HERE, "publish.py")])
        return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
