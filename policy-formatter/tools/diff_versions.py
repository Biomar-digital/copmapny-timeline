#!/usr/bin/env python3
"""
Pre-compute, for consecutive editions of each policy:
  * a side-by-side word-highlighted text diff, and
  * rendered page images with the CHANGED regions boxed, so the dashboard can
    show the two real documents next to each other, scroll-synced, with the
    changes marked — without parsing PDFs in the browser.

Writes docs/diffs.json and page PNGs under docs/files/cmp/<policy>/<version>/.

Usage:  python policy-formatter/tools/diff_versions.py
"""
import difflib
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
LIBRARY = os.path.join(REPO, "docs", "library.json")
OUT = os.path.join(REPO, "docs", "diffs.json")
CMP_DIR = os.path.join(REPO, "docs", "files", "cmp")
DPI = 120


_CARD = ("Version history", "Owner and approver", "Powered by Partnership",
         "Driven by Innovation")
def is_furniture(t, title):
    tl = t.strip()
    if not tl or tl == "BioMar Group" or tl == title:
        return True
    if "BioMar Group A/S" in tl or "www.biomar.com" in tl:
        return True
    if tl in _CARD or tl.startswith(("Owner:", "Approver:", "Approval date:")) or \
       re.match(r"^Version\s+[\d.]+:", tl):
        return True                      # back-cover version/owner card — not content
    return bool(re.fullmatch(r"\d{1,3}", tl))


def load_blocks(pdf_rel, title):
    import fitz
    d = fitz.open(os.path.join(REPO, "docs", pdf_rel))
    blocks = []  # (page_index, text)
    for pg in range(d.page_count):
        for ln in d[pg].get_text().splitlines():
            t = ln.strip()
            if not is_furniture(t, title):
                blocks.append((pg, re.sub(r"\s+", " ", t)))
    return blocks, d


def word_flags(a, b):
    aw, bw = a.split(" "), b.split(" ")
    sm = difflib.SequenceMatcher(None, aw, bw)
    la, lb, cha, chb = [], [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        f = 0 if tag == "equal" else 1
        for w in aw[i1:i2]:
            la.append([w, f if tag != "insert" else 0])
            if tag in ("replace", "delete"):
                cha.append(w)
        for w in bw[j1:j2]:
            lb.append([w, f if tag != "delete" else 0])
            if tag in ("replace", "insert"):
                chb.append(w)
    return la, lb, " ".join(cha).strip(), " ".join(chb).strip()


def rects_for(page, phrase):
    """Normalised rects (0-1) marking a changed line on a page (best-effort).
    Tries the whole phrase, then a punctuation-stripped version."""
    phrase = (phrase or "").strip()
    if len(phrase) < 2:
        return []
    pr = page.rect
    tries = [phrase[:150]]
    clean = re.sub(r"[()\[\]“”\"']", "", phrase).strip()
    if clean and clean != phrase:
        tries.append(clean[:150])
    for t in tries:
        hits = page.search_for(t, quads=False) or []
        if hits:
            return [{"x": r.x0 / pr.width, "y": r.y0 / pr.height,
                     "w": (r.x1 - r.x0) / pr.width, "h": (r.y1 - r.y0) / pr.height}
                    for r in hits]
    return []


def render_pages(doc, policy_id, version, side):
    """Render each page to a PNG; return list of {img, w, h}."""
    vdir = os.path.join(CMP_DIR, policy_id, version.replace(" ", "_") + "_" + side)
    os.makedirs(vdir, exist_ok=True)
    pages = []
    for i in range(doc.page_count):
        pix = doc[i].get_pixmap(dpi=DPI)
        rel = os.path.relpath(os.path.join(vdir, f"p{i+1}.png"), os.path.join(REPO, "docs"))
        pix.save(os.path.join(REPO, "docs", rel))
        pages.append({"img": rel, "w": pix.width, "h": pix.height, "rects": []})
    return pages


def build_pair(policy_id, title, old_ed, new_ed):
    def pdf(ed):
        d0 = (ed.get("documents") or [{}])[0]
        return (d0.get("files") or {}).get("non_approval")
    po, pn = pdf(old_ed), pdf(new_ed)
    if not po or not pn:
        return None
    ob, od = load_blocks(po, title)
    nb, nd = load_blocks(pn, title)
    ot = [t for _, t in ob]
    nt = [t for _, t in nb]

    pages_old = render_pages(od, policy_id, old_ed["version"], "old")
    pages_new = render_pages(nd, policy_id, new_ed["version"], "new")

    rows = []
    sm = difflib.SequenceMatcher(None, ot, nt)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for off in range(i2 - i1):
                rows.append({"t": "eq", "l": [[ot[i1 + off], 0]], "r": [[nt[j1 + off], 0]]})
        elif tag == "delete":
            for k in range(i1, i2):
                rows.append({"t": "del", "l": [[ot[k], 1]], "r": []})
                for rc in rects_for(od[ob[k][0]], ot[k]):
                    pages_old[ob[k][0]]["rects"].append(rc)
        elif tag == "insert":
            for k in range(j1, j2):
                rows.append({"t": "ins", "l": [], "r": [[nt[k], 1]]})
                for rc in rects_for(nd[nb[k][0]], nt[k]):
                    pages_new[nb[k][0]]["rects"].append(rc)
        else:
            oc, nc = list(range(i1, i2)), list(range(j1, j2))
            for k in range(max(len(oc), len(nc))):
                lo = ot[oc[k]] if k < len(oc) else ""
                nw = nt[nc[k]] if k < len(nc) else ""
                if lo and nw:
                    la, lb, cha, chb = word_flags(lo, nw)
                    rows.append({"t": "chg", "l": la, "r": lb})
                    for rc in rects_for(od[ob[oc[k]][0]], lo):
                        pages_old[ob[oc[k]][0]]["rects"].append(rc)
                    for rc in rects_for(nd[nb[nc[k]][0]], nw):
                        pages_new[nb[nc[k]][0]]["rects"].append(rc)
                elif lo:
                    rows.append({"t": "del", "l": [[lo, 1]], "r": []})
                    for rc in rects_for(od[ob[oc[k]][0]], lo):
                        pages_old[ob[oc[k]][0]]["rects"].append(rc)
                else:
                    rows.append({"t": "ins", "l": [], "r": [[nw, 1]]})
                    for rc in rects_for(nd[nb[nc[k]][0]], nw):
                        pages_new[nb[nc[k]][0]]["rects"].append(rc)
    changed = sum(1 for r in rows if r["t"] != "eq")
    return {"old": old_ed["version"], "new": new_ed["version"],
            "changed": changed, "rows": rows,
            "pages_old": pages_old, "pages_new": pages_new}


def main():
    lib = json.load(open(LIBRARY, encoding="utf-8"))
    if os.path.isdir(CMP_DIR):
        shutil.rmtree(CMP_DIR)
    diffs = {}
    for p in lib["policies"]:
        eds = p.get("editions", [])
        if len(eds) < 2:
            continue
        for i in range(1, len(eds)):
            try:
                pair = build_pair(p["id"], p.get("title", ""), eds[i - 1], eds[i])
            except Exception as e:
                print("  skip", p["id"], e); continue
            if not pair:
                continue
            key = f"{eds[i].get('version')}__{eds[i-1].get('version')}"
            diffs.setdefault(p["id"], {})[key] = pair
            print(f"  {p['id']}: {pair['old']} → {pair['new']}  ({pair['changed']} changed lines)")
    json.dump(diffs, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    open(OUT, "a").write("\n")
    print("wrote", os.path.relpath(OUT, REPO), "-", len(diffs), "policies")


if __name__ == "__main__":
    main()
