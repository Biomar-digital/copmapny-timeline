#!/usr/bin/env python3
"""
Serve a policy document as its original PDF (verbatim), instead of re-rendering
it from the extracted source.

Design-heavy pieces — position statements, the Code of Conduct, anything with a
custom cover, colour artwork, infographics or hand-tuned multi-column
typesetting — cannot be reproduced byte-for-byte by the formatter. For those we
keep the editable .docx in policies/sources/ (so the text can still be revised)
but publish the official PDF as-is so the library shows the exact original.

This copies the chosen PDF into policies/sources/ and flips the matching
registry document to `pdf:` mode (publish.py then copies it through untouched).

    python tools/use_original.py --id <policy-id> --pdf <original.pdf> [--label <label>]

`--label` is only needed to disambiguate a policy that has several documents in
the same edition; by default the single document is updated.
List the policies and their documents:

    python tools/use_original.py --list
"""
import argparse
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
SOURCES = os.path.join(REPO, "policies", "sources")
REGISTRY = os.path.join(REPO, "policies", "registry.json")


def _slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def _load():
    return json.load(open(REGISTRY, encoding="utf-8"))


def _save(reg):
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _documents(ed):
    if ed.get("documents"):
        return ed["documents"]
    # normalise a legacy flat edition into the documents schema
    doc = {"label": "Policy", "language": None, "source": ed.get("source"),
           "board_approval": ed.get("board_approval", True)}
    ed["documents"] = [doc]
    return ed["documents"]


def list_policies():
    reg = _load()
    for p in reg["policies"]:
        print(f"{p['id']:30}  {p['title']}")
        for ei, ed in enumerate(p.get("editions", [])):
            for d in _documents(ed):
                mode = "original-pdf" if d.get("pdf") else "re-rendered"
                print(f"    ed{ei} label={d.get('label')!r:18} {mode}")


def use_original(pid, pdf_path, label):
    if not os.path.exists(pdf_path):
        sys.exit(f"PDF not found: {pdf_path}")
    reg = _load()
    pol = next((p for p in reg["policies"] if p["id"] == pid), None)
    if pol is None:
        sys.exit(f"No policy with id {pid!r}. Use --list to see ids.")

    # Find the target document (across editions) by label, or the only document.
    targets = []
    for ed in pol.get("editions", []):
        for d in _documents(ed):
            if label is None or d.get("label") == label:
                targets.append(d)
    if not targets:
        sys.exit(f"No document matching label={label!r} in {pid!r}.")
    if len(targets) > 1 and label is None:
        labels = ", ".join(repr(d.get("label")) for d in targets)
        sys.exit(f"{pid!r} has several documents ({labels}); pass --label.")

    os.makedirs(SOURCES, exist_ok=True)
    dest_name = f"{_slug(pid)}__original.pdf"
    dest = os.path.join(SOURCES, dest_name)
    shutil.copyfile(pdf_path, dest)

    for d in targets:
        d["pdf"] = dest_name            # publish.py copies this through as-is
        d.pop("board_approval", None)   # design pieces have no board page
    _save(reg)
    print(f"✓ {pid}: now served from original PDF -> policies/sources/{dest_name}")
    print(f"  (editable source kept for future text edits; run publish.py to apply)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", help="policy id (see --list)")
    ap.add_argument("--pdf", help="path to the official PDF to publish verbatim")
    ap.add_argument("--label", default=None, help="document label to disambiguate")
    ap.add_argument("--list", action="store_true", help="list policies and documents")
    a = ap.parse_args()
    if a.list:
        list_policies()
        return
    if not (a.id and a.pdf):
        ap.error("--id and --pdf are required (or use --list)")
    use_original(a.id, a.pdf, a.label)


if __name__ == "__main__":
    main()
