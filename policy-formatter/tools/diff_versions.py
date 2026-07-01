#!/usr/bin/env python3
"""
Pre-compute a side-by-side, word-highlighted diff between consecutive editions
of each policy, so the dashboard can show "what changed" without parsing PDFs in
the browser. Writes docs/diffs.json:

  { "<policy_id>": { "<newVer>__<oldVer>": {
        "old": "Version 2", "new": "Version 2.1",
        "rows": [ {"t":"eq|del|ins|chg", "l":[[text,flag],..], "r":[[text,flag],..]}, ... ]
  } } }

flag: 0 = unchanged word, 1 = changed word (highlight).

Usage:  python policy-formatter/tools/diff_versions.py
"""
import difflib
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
LIBRARY = os.path.join(REPO, "docs", "library.json")
OUT = os.path.join(REPO, "docs", "diffs.json")


def is_furniture(t, title):
    tl = t.strip()
    if not tl:
        return True
    if tl == "BioMar Group" or tl == title:
        return True
    if "BioMar Group A/S" in tl or "www.biomar.com" in tl:
        return True
    if re.fullmatch(r"\d{1,3}", tl):        # page number
        return True
    return False


def blocks(pdf_rel, title):
    import fitz
    d = fitz.open(os.path.join(REPO, "docs", pdf_rel))
    out = []
    for pg in range(d.page_count):
        for ln in d[pg].get_text().splitlines():
            t = ln.strip()
            if not is_furniture(t, title):
                out.append(re.sub(r"\s+", " ", t))
    return out


def word_diff(a, b):
    """Return (a_tokens, b_tokens) with per-word change flags."""
    aw, bw = a.split(" "), b.split(" ")
    sm = difflib.SequenceMatcher(None, aw, bw)
    la, lb = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        f = 0 if tag == "equal" else 1
        for w in aw[i1:i2]:
            la.append([w, f if tag != "insert" else 0])
        for w in bw[j1:j2]:
            lb.append([w, f if tag != "delete" else 0])
    return la, lb


def plain(line):
    return [[line, 0]]


def diff_pair(old_blocks, new_blocks):
    sm = difflib.SequenceMatcher(None, old_blocks, new_blocks)
    rows = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                rows.append({"t": "eq", "l": plain(old_blocks[k]), "r": plain(new_blocks[k])})
        elif tag == "delete":
            for k in range(i1, i2):
                rows.append({"t": "del", "l": [[old_blocks[k], 1]], "r": []})
        elif tag == "insert":
            for k in range(j1, j2):
                rows.append({"t": "ins", "l": [], "r": [[new_blocks[k], 1]]})
        else:  # replace — align 1:1 with word-level highlight
            oldc, newc = old_blocks[i1:i2], new_blocks[j1:j2]
            for k in range(max(len(oldc), len(newc))):
                lo = oldc[k] if k < len(oldc) else ""
                nw = newc[k] if k < len(newc) else ""
                if lo and nw:
                    la, lb = word_diff(lo, nw)
                    rows.append({"t": "chg", "l": la, "r": lb})
                elif lo:
                    rows.append({"t": "del", "l": [[lo, 1]], "r": []})
                else:
                    rows.append({"t": "ins", "l": [], "r": [[nw, 1]]})
    return rows


def main():
    lib = json.load(open(LIBRARY, encoding="utf-8"))
    diffs = {}
    for p in lib["policies"]:
        eds = p.get("editions", [])
        if len(eds) < 2:
            continue
        title = p.get("title", "")
        for i in range(1, len(eds)):
            old, new = eds[i - 1], eds[i]

            def pdf(ed):
                d0 = (ed.get("documents") or [{}])[0]
                return (d0.get("files") or {}).get("non_approval")
            po, pn = pdf(old), pdf(new)
            if not po or not pn:
                continue
            try:
                rows = diff_pair(blocks(po, title), blocks(pn, title))
            except Exception as e:
                print("  skip", p["id"], e); continue
            changed = sum(1 for r in rows if r["t"] != "eq")
            key = f"{new.get('version')}__{old.get('version')}"
            diffs.setdefault(p["id"], {})[key] = {
                "old": old.get("version"), "new": new.get("version"),
                "old_date": old.get("date"), "new_date": new.get("date"),
                "changed": changed, "rows": rows,
            }
            print(f"  {p['id']}: {old.get('version')} → {new.get('version')}  ({changed} changed lines)")
    json.dump(diffs, open(OUT, "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"))
    open(OUT, "a").write("\n")
    print("wrote", os.path.relpath(OUT, REPO), "-", len(diffs), "policies with diffs")


if __name__ == "__main__":
    main()
