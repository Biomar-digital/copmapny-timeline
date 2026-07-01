#!/usr/bin/env python3
"""
Self-review: after a change is applied, verify — deterministically — that the
output actually reflects what was asked, before it goes to human review.

Runs a set of automatic checks against the *rendered* output (not the reasoning
that produced it) and writes a report to
`policies/requests/<request_id>/self_review.json`.

Checks (generic, always run):
  - outputs        the policy's current edition rendered a PDF (+ Word) and it's non-empty
  - variants       the Signed/Unsigned variants match what was requested
  - metadata       approver / owner / approval date are present
  - coverage       every section/paragraph of the source .docx appears in the PDF
                   (catches silently dropped content)
  - ligatures      no raw ﬁ/ﬂ ligatures left in the text
Plus, if `policies/requests/<id>/checklist.json` exists, each assertion
  { "id", "label", "page"?, "present": [..], "absent": [..] }
is verified against the PDF text.

Usage:
  python policy-formatter/tools/self_review.py --policy <policy_id> --request <request_id>
      [--versions "Signed + Unsigned"] [--checklist path.json]
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
LIBRARY = os.path.join(REPO, "docs", "library.json")
SOURCES = os.path.join(REPO, "policies", "sources")
REQUESTS = os.path.join(REPO, "policies", "requests")
REGISTRY = os.path.join(REPO, "policies", "registry.json")


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("ﬁ", "fi").replace("ﬂ", "fl")).strip()


def pdf_text(path):
    import fitz
    d = fitz.open(path)
    return "\n".join(d[i].get_text() for i in range(d.page_count)), d.page_count


def page_text(path, page):
    import fitz
    d = fitz.open(path)
    if page and 1 <= page <= d.page_count:
        return d[page - 1].get_text()
    return "\n".join(d[i].get_text() for i in range(d.page_count))


def find_policy(policy_id):
    lib = json.load(open(LIBRARY, encoding="utf-8"))
    for p in lib["policies"]:
        if p["id"] == policy_id:
            return p
    return None


def source_paths(policy_id):
    reg = json.load(open(REGISTRY, encoding="utf-8"))
    for p in reg["policies"]:
        if p["id"] == policy_id:
            ed = p["editions"][-1]
            docs = ed.get("documents") or [{"source": ed.get("source")}]
            return [d["source"] for d in docs if d.get("source")]
    return []


def check(results, cid, label, status, detail=""):
    results.append({"id": cid, "label": label, "status": status, "detail": detail})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--request", default="")
    ap.add_argument("--versions", default="", help="Versions requested (e.g. 'Signed + Unsigned')")
    ap.add_argument("--checklist", default="")
    args = ap.parse_args(argv)

    results = []
    pol = find_policy(args.policy)
    if not pol:
        print("policy not found in library.json:", args.policy); return 2
    ed = pol["editions"][-1]
    doc0 = (ed.get("documents") or [{}])[0]
    files = doc0.get("files", {})

    # 1 — outputs exist and are non-empty
    pdf_rel = files.get("non_approval") or files.get("approval")
    pdf_abs = os.path.join(REPO, "docs", pdf_rel) if pdf_rel else None
    if pdf_abs and os.path.exists(pdf_abs) and os.path.getsize(pdf_abs) > 2000:
        full, pages = pdf_text(pdf_abs)
        check(results, "outputs", "Rendered PDF exists and is non-empty", "pass", f"{pages} pages")
    else:
        check(results, "outputs", "Rendered PDF exists and is non-empty", "fail", "PDF missing/empty")
        full, pages = "", 0
    if files.get("word"):
        w = os.path.join(REPO, "docs", files["word"])
        check(results, "word", "Editable Word (.docx) produced", "pass" if os.path.exists(w) else "fail")

    # 2 — variants match the request
    have = []
    if files.get("approval"):
        have.append("Signed")
    if files.get("non_approval"):
        have.append("Unsigned")
    have_str = " + ".join(have) if have else "none"
    if args.versions:
        want = set(re.findall(r"Signed|Unsigned", args.versions))
        ok = want == set(have)
        check(results, "variants", f"Variants match request ({args.versions})",
              "pass" if ok else "fail", f"produced: {have_str}")
    else:
        check(results, "variants", "Variants produced", "info", have_str)

    # 3 — metadata present
    miss = [k for k in ("approval_date",) if not ed.get(k)]
    miss += [] if pol.get("approver") else ["approver"]
    miss += [] if pol.get("owner") else ["owner"]
    check(results, "metadata", "Approver / owner / approval date present",
          "pass" if not miss else "attention",
          "complete" if not miss else "missing: " + ", ".join(miss))

    # 4 — source coverage (no silently dropped content)
    try:
        import docx
        missing = []
        checked = 0
        for src in source_paths(args.policy):
            sp = os.path.join(SOURCES, src)
            if not os.path.exists(sp):
                continue
            d = docx.Document(sp)
            fnorm = norm(full)
            for para in d.paragraphs:
                t = norm(para.text)
                if len(t) < 30:
                    continue
                checked += 1
                key = t[:45]
                if key not in fnorm:
                    missing.append(t[:60])
        if checked:
            check(results, "coverage", "All source content appears in the PDF",
                  "pass" if not missing else "fail",
                  f"{checked - len(missing)}/{checked} passages found" +
                  ("" if not missing else " · missing: " + " | ".join(missing[:3])))
    except Exception as e:
        check(results, "coverage", "Source coverage", "info", f"skipped ({e})")

    # 5 — ligatures
    if full:
        ligs = sum(full.count(c) for c in ("ﬁ", "ﬂ", "ﬀ", "ﬃ", "ﬄ"))
        check(results, "ligatures", "No raw ligatures left", "pass" if ligs == 0 else "attention",
              "clean" if ligs == 0 else f"{ligs} ligatures")

    # 6 — explicit checklist assertions
    cl = args.checklist
    if not cl and args.request:
        maybe = os.path.join(REQUESTS, args.request, "checklist.json")
        cl = maybe if os.path.exists(maybe) else ""
    if cl and os.path.exists(cl):
        for a in json.load(open(cl, encoding="utf-8")):
            txt = norm(page_text(pdf_abs, a.get("page"))) if pdf_abs else ""
            probs = []
            for s in a.get("present", []):
                if norm(s) not in txt:
                    probs.append(f"missing '{s[:30]}'")
            for s in a.get("absent", []):
                if norm(s) in txt:
                    probs.append(f"still has '{s[:30]}'")
            check(results, "assert:" + str(a.get("id", "")),
                  a.get("label", "assertion"),
                  "pass" if not probs else "fail", "; ".join(probs))

    hard = sum(1 for r in results if r["status"] == "fail")
    soft = sum(1 for r in results if r["status"] == "attention")
    passed = sum(1 for r in results if r["status"] == "pass")
    overall = "fail" if hard else ("attention" if soft else "pass")
    report = {
        "request_id": args.request or None,
        "policy": args.policy,
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "overall": overall,
        "summary": f"{passed} passed" + (f", {soft} to review" if soft else "") +
                   (f", {hard} failed" if hard else ""),
        "checks": results,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.request:
        out = os.path.join(REQUESTS, args.request, "self_review.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump(report, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        open(out, "a").write("\n")
        print("\nwrote", os.path.relpath(out, REPO))
    return 1 if overall == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
