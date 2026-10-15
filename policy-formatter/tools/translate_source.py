#!/usr/bin/env python3
"""
Translate a policy's Word source into another language WITHOUT losing structure.

A translation is a new source .docx that is a copy of the English one with only
the wording swapped, so numbering, styles, tables, footnotes and every clause
marker survive byte-for-byte; it then goes through the normal publish pipeline
(registry entry with `translation_of`, rendered with the target language's own
card labels — see i18n.py).

    # 1. dump every translatable paragraph (body, table cells, footnotes) to JSON
    python policy-formatter/tools/translate_source.py extract policies/sources/X.docx -o /tmp/x.segments.json
    #    (after the English changed: add  --reuse OLD_X.docx policies/sources/X__es.docx  so only
    #     new/edited paragraphs need translating — recover OLD_X.docx with `git show <ref>:path`)

    # 2. fill in "translation" for each segment (Claude does this in a session; or
    #    skip steps 1-3 entirely when the requester attached a translated Word file)

    # 3. write the translated copy
    python policy-formatter/tools/translate_source.py apply policies/sources/X.docx \\
        /tmp/x.segments.json -o policies/sources/X__es.docx

    # 4. prove nothing was dropped / reordered (also run by self_review.py)
    python policy-formatter/tools/translate_source.py verify policies/sources/X.docx policies/sources/X__es.docx

Segment text carries lightweight inline markup so a translation can reorder
words and still keep formatting: <b>..</b>, <i>..</i> (only present when a
paragraph MIXES styles; a uniformly bold heading has no tags) and [[fn:ID]] /
[[keep:N]] placeholders for footnote references / images / fields, which must be
copied through exactly. A leading clause marker ("(a)", "3.1.2") is split off as
`prefix` and is never translated.
"""
import argparse
import copy
import hashlib
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..")))

import docx  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.text.run import Run  # noqa: E402
from docx.text.paragraph import Paragraph  # noqa: E402
from docx.table import Table  # noqa: E402
from docx.oxml.table import CT_Tbl  # noqa: E402
from docx.oxml.text.paragraph import CT_P  # noqa: E402

# "(a)\t", "3.1.2 ", "1.\t", "(iv)\t" — a clause marker we must never touch.
_PREFIX = re.compile(r"^\s*((?:\([A-Za-z0-9]{1,5}\)|\d{1,3}(?:\.\d{1,3})*\.?|[A-Za-z]\)|[•–\-])(?:\t+|[ ]+))")
_TOKEN = re.compile(r"\[\[(fn|keep):([^\]]+)\]\]")
_NUMBER = re.compile(r"\d[\d.,/:\-]*\d|\d")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


# --------------------------------------------------------------------------
# paragraph <-> markup
# --------------------------------------------------------------------------
_NESTED = {qn("w:txbxContent"), qn("w:drawing"), qn("w:pict"), qn("w:object")}


def _runs(p_el):
    """Every w:r of THIS paragraph in order, including those wrapped in
    hyperlinks / smart tags (python-docx's Paragraph.runs skips those) but not
    the ones inside a text box / drawing, which are other paragraphs (and which
    Word stores twice, as AlternateContent Choice + Fallback)."""
    out = []
    for r in p_el.iter(qn("w:r")):
        anc, nested = r.getparent(), False
        while anc is not None and anc is not p_el:
            if anc.tag in _NESTED:
                nested = True
                break
            anc = anc.getparent()
        if not nested:
            out.append(r)
    return out


def _protected(r_el):
    """A run that is not plain text: footnote reference, image, field char."""
    if r_el.find(qn("w:footnoteReference")) is not None:
        return "fn", r_el.find(qn("w:footnoteReference")).get(qn("w:id"))
    if r_el.find(qn("w:footnoteRef")) is not None:
        return "keep", "fnref"
    for tag in ("w:drawing", "w:pict", "w:object", "w:fldChar", "w:instrText", "w:sym"):
        if r_el.find(qn(tag)) is not None:
            return "keep", tag.split(":")[1]
    return None


def _flags(r_el):
    rpr = r_el.find(qn("w:rPr"))
    def on(tag):
        if rpr is None:
            return False
        el = rpr.find(qn(tag))
        if el is None:
            return False
        return el.get(qn("w:val"), "true").lower() not in ("0", "false", "off")
    return on("w:b"), on("w:i")


def paragraph_markup(p_el, parent):
    """-> (prefix, markup, mixed) for a paragraph element, or None when it has
    nothing to translate."""
    pieces = []        # (kind, payload, bold, italic)
    keep_n = 0
    for r in _runs(p_el):
        prot = _protected(r)
        if prot:
            kind, ident = prot
            if kind == "keep":
                keep_n += 1
                ident = f"{ident}{keep_n}"
            pieces.append(("tok", f"[[{kind}:{ident}]]", False, False))
            continue
        txt = Run(r, parent).text
        if not txt:
            continue
        b, i = _flags(r)
        pieces.append(("txt", txt, b, i))
    full = "".join(p for k, p, _, _ in pieces if k == "txt")
    if not re.search(r"[^\W\d_]", full):         # no letters at all -> nothing to translate
        return None
    m = _PREFIX.match(full)
    prefix = m.group(1) if m else ""
    skip = len(prefix)
    # drop the prefix characters from the front of the text pieces
    trimmed = []
    for kind, payload, b, i in pieces:
        if kind == "txt" and skip > 0:
            if len(payload) <= skip:
                skip -= len(payload)
                continue
            payload = payload[skip:]
            skip = 0
        trimmed.append((kind, payload, b, i))
    txts = [(b, i) for k, _, b, i in trimmed if k == "txt"]
    mixed = len(set(txts)) > 1
    out = []
    for kind, payload, b, i in trimmed:
        if kind == "tok":
            out.append(payload)
            continue
        s = html.escape(payload, quote=False)
        if mixed:
            if i:
                s = f"<i>{s}</i>"
            if b:
                s = f"<b>{s}</b>"
        out.append(s)
    markup = "".join(out)
    if mixed:                       # merge adjacent identical tags: </b><b> -> ""
        for tag in ("b", "i"):
            markup = markup.replace(f"</{tag}><{tag}>", "")
    return prefix, markup, mixed


_MARK = re.compile(r"(<b>|</b>|<i>|</i>|\[\[(?:fn|keep):[^\]]+\]\])")


def parse_markup(markup):
    """markup -> [(text, bold, italic, token)] ; token is a '[[..]]' string."""
    out, b, i = [], False, False
    for part in _MARK.split(markup):
        if not part:
            continue
        if part == "<b>": b = True
        elif part == "</b>": b = False
        elif part == "<i>": i = True
        elif part == "</i>": i = False
        elif part.startswith("[["): out.append(("", False, False, part))
        else: out.append((html.unescape(part), b, i, None))
    return out


def _set_flag(rpr, tag, on):
    el = rpr.find(qn(tag))
    if on:
        if el is None:
            el = OxmlElement(tag); rpr.append(el)
        if qn("w:val") in el.attrib:
            del el.attrib[qn("w:val")]
    else:
        if el is not None:
            rpr.remove(el)


def apply_markup(p_el, parent, prefix, markup, mixed_hint=True):
    """Rewrite a paragraph's runs from translated markup, keeping paragraph
    properties and the first text run's character formatting."""
    runs = _runs(p_el)
    text_runs = [r for r in runs if not _protected(r)]
    protected = {}
    keep_n = 0
    for r in runs:
        prot = _protected(r)
        if prot:
            kind, ident = prot
            if kind == "keep":
                keep_n += 1
                ident = f"{ident}{keep_n}"
            protected[f"[[{kind}:{ident}]]"] = r
    base = None
    for r in text_runs:
        if Run(r, parent).text:
            base = r
            break
    base_rpr = copy.deepcopy(base.find(qn("w:rPr"))) if base is not None and base.find(qn("w:rPr")) is not None else None
    parts = parse_markup(markup)
    tags_used = "<b>" in markup or "<i>" in markup
    # remove every old run (and any hyperlink wrappers); protected runs re-inserted below
    for r in runs:
        par = r.getparent()
        par.remove(r)
    for tag in ("w:hyperlink", "w:smartTag"):
        for el in list(p_el.iter(qn(tag))):
            if len(el) == 0:
                el.getparent().remove(el)

    def new_run(text, b=None, i=None):
        r = OxmlElement("w:r")
        if base_rpr is not None:
            rpr = copy.deepcopy(base_rpr)
        else:
            rpr = OxmlElement("w:rPr")
        if tags_used:                       # mixed paragraph: formatting is absolute
            _set_flag(rpr, "w:b", bool(b))
            _set_flag(rpr, "w:i", bool(i))
        if len(rpr):
            r.append(rpr)
        # tabs / line breaks round-trip as real elements
        buf = ""
        for ch in text:
            if ch in "\t\n":
                if buf:
                    t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve"); t.text = buf; r.append(t); buf = ""
                r.append(OxmlElement("w:tab" if ch == "\t" else "w:br"))
            else:
                buf += ch
        if buf:
            t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve"); t.text = buf; r.append(t)
        return r

    if prefix:
        p_el.append(new_run(prefix, False, False) if tags_used else new_run(prefix))
    for text, b, i, tok in parts:
        if tok:
            r = protected.get(tok)
            if r is None:
                raise ValueError(f"placeholder {tok} not present in the source paragraph")
            p_el.append(r)
        else:
            p_el.append(new_run(text, b, i))
    unused = [t for t in protected if t not in {p[3] for p in parts if p[3]}]
    if unused:
        raise ValueError(f"translation dropped placeholder(s) {unused}")


# --------------------------------------------------------------------------
# document walking
# --------------------------------------------------------------------------
def _walk(doc):
    """Yield (id, p_element, parent) for every paragraph in body order,
    including table cells (deduplicated for merged cells) and footnotes."""
    body = doc.element.body
    counter = {"p": 0, "t": 0}

    def block(parent_el, parent_obj, prefix):
        for child in parent_el.iterchildren():
            if isinstance(child, CT_P):
                counter["p"] += 1
                yield f"{prefix}p{counter['p']}", child, parent_obj
            elif isinstance(child, CT_Tbl):
                counter["t"] += 1
                tid = f"{prefix}t{counter['t']}"
                tbl = Table(child, parent_obj)
                seen = set()
                for ri, row in enumerate(tbl.rows):
                    for ci, cell in enumerate(row.cells):
                        # hold the element itself, not id(): lxml proxies are
                        # recycled, so ids collide and cells get skipped
                        if cell._tc in seen:
                            continue
                        seen.add(cell._tc)
                        sub = 0
                        for el in cell._tc.iterchildren():
                            if isinstance(el, CT_P):
                                sub += 1
                                yield f"{tid}r{ri}c{ci}p{sub}", el, cell
                            elif isinstance(el, CT_Tbl):
                                counter["t"] += 1
                                yield from block(cell._tc, cell, f"{tid}r{ri}c{ci}")  # nested tables
                                break
    yield from block(body, doc, "")


def _footnote_root(doc):
    from lxml import etree
    try:
        rel = next(r for r in doc.part.rels.values() if r.reltype.endswith("/footnotes"))
    except StopIteration:
        return None, None
    return rel.target_part, etree.fromstring(rel.target_part.blob)


def _footnote_paras(root):
    for fn in root.findall(qn("w:footnote")):
        if fn.get(qn("w:type")) in ("separator", "continuationSeparator"):
            continue
        fid = fn.get(qn("w:id"))
        for k, p in enumerate(fn.findall(qn("w:p")), 1):
            yield f"fn{fid}p{k}", p


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_extract(args):
    doc = docx.Document(args.source)
    segs = []
    for sid, p_el, parent in _walk(doc):
        res = paragraph_markup(p_el, parent)
        if res:
            prefix, markup, mixed = res
            if not markup.strip():
                continue
            segs.append({"id": sid, "prefix": prefix, "text": markup, "translation": ""})
    part, root = _footnote_root(doc)
    if root is not None:
        for sid, p_el in _footnote_paras(root):
            res = paragraph_markup(p_el, doc)
            if res and res[1].strip():
                segs.append({"id": sid, "prefix": res[0], "text": res[1], "translation": ""})
    reused = 0
    if args.reuse:
        # Re-translating after the English changed: keep the wording of every
        # paragraph whose English is unchanged, leave only new/edited ones blank.
        old_en, old_tr = args.reuse
        known = {}
        for a, b in zip(_fingerprint_text(old_en), _fingerprint_text(old_tr)):
            if a[0] == b[0]:                              # same paragraph id in both
                known[(a[1], a[2])] = b[2]
        for sg in segs:
            hit = known.get((sg["prefix"].strip(), sg["text"]))
            if hit:
                sg["translation"] = hit
                reused += 1
    full = " ".join(s["text"] for s in segs)
    terms = sorted({m for m in re.findall(r"“([^”]{2,40})”", full)})
    out = {"source": os.path.basename(args.source), "source_sha": sha(args.source),
           "target_language": args.language or "", "glossary": {t: "" for t in terms},
           "segments": segs}
    json.dump(out, open(args.output, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"extracted {len(segs)} segments ({reused} reused from the previous translation, "
          f"{len(segs) - reused} to translate), {len(terms)} defined terms -> {args.output}")


def _fingerprint_text(path):
    """[(paragraph id, prefix, markup)] in document order (body + footnotes)."""
    doc = docx.Document(path)
    out = []
    for sid, p_el, parent in _walk(doc):
        res = paragraph_markup(p_el, parent)
        if res and res[1].strip():
            out.append((sid, res[0].strip(), res[1]))
    part, root = _footnote_root(doc)
    if root is not None:
        for sid, p_el in _footnote_paras(root):
            res = paragraph_markup(p_el, doc)
            if res and res[1].strip():
                out.append((sid, res[0].strip(), res[1]))
    return out


def _load_translations(paths):
    merged, meta = {}, None
    for path in paths:
        d = json.load(open(path, encoding="utf-8"))
        meta = meta or d
        if isinstance(d, dict) and "segments" in d:
            for s in d["segments"]:
                if s.get("translation"):
                    merged[s["id"]] = s["translation"]
        else:                                    # plain {id: translation} chunk
            merged.update({k: v for k, v in d.items() if isinstance(v, str)})
    return merged, meta


def cmd_apply(args):
    doc = docx.Document(args.source)
    tr, meta = _load_translations(args.translations)
    if meta and meta.get("source_sha") and meta["source_sha"] != sha(args.source) and not args.force:
        sys.exit("source docx changed since `extract` (sha mismatch) — re-extract, or pass --force")
    # prefixes come from the source, so a translation can never alter a marker
    done, missing = set(), []
    for sid, p_el, parent in _walk(doc):
        res = paragraph_markup(p_el, parent)
        if not res or not res[1].strip():
            continue
        prefix, markup, _ = res
        if sid not in tr:
            missing.append(sid); continue
        apply_markup(p_el, parent, prefix, tr[sid]); done.add(sid)
    part, root = _footnote_root(doc)
    if root is not None:
        from lxml import etree
        for sid, p_el in _footnote_paras(root):
            res = paragraph_markup(p_el, doc)
            if not res or not res[1].strip():
                continue
            if sid not in tr:
                missing.append(sid); continue
            apply_markup(p_el, doc, res[0], tr[sid]); done.add(sid)
        part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    extra = [k for k in tr if k not in done]
    if missing and not args.allow_missing:
        sys.exit(f"{len(missing)} segment(s) have no translation (e.g. {missing[:5]}) — "
                 "fill them in, or pass --allow-missing to keep the source wording for those")
    if extra:
        sys.exit(f"translation ids that match nothing in the source: {extra[:8]}")
    doc.save(args.output)
    print(f"translated {len(done)} paragraph(s), kept source wording for {len(missing)} -> {args.output}")


# ---- verification -----------------------------------------------------------
def _fingerprint(path):
    """Ordered structural fingerprint: one entry per translatable paragraph."""
    doc = docx.Document(path)
    out = []
    for sid, p_el, parent in _walk(doc):
        res = paragraph_markup(p_el, parent)
        if res and res[1].strip():
            prefix, markup, mixed = res
            plain = re.sub(r"<[^>]+>|\[\[[^\]]+\]\]", "", markup)
            out.append({
                "id": sid, "prefix": prefix.strip(),
                "tokens": _TOKEN.findall(markup),
                "bold": markup.count("<b>"), "numbers": sorted(_NUMBER.findall(html.unescape(plain))),
                "words": len(plain.split()),
            })
    part, root = _footnote_root(doc)
    if root is not None:
        for sid, p_el in _footnote_paras(root):
            res = paragraph_markup(p_el, doc)
            if res and res[1].strip():
                plain = re.sub(r"<[^>]+>|\[\[[^\]]+\]\]", "", res[1])
                out.append({"id": sid, "prefix": res[0].strip(), "tokens": _TOKEN.findall(res[1]),
                            "bold": res[1].count("<b>"), "numbers": sorted(_NUMBER.findall(html.unescape(plain))),
                            "words": len(plain.split())})
    return out


def compare(src_path, tr_path, strict=True):
    """-> (errors, warnings). strict: same paragraph ids in the same order;
    otherwise (a translation supplied as a separately-authored Word file) only
    the ordered clause markers are compared."""
    a, b = _fingerprint(src_path), _fingerprint(tr_path)
    errors, warnings = [], []
    if strict:
        ia, ib = [x["id"] for x in a], [x["id"] for x in b]
        if ia != ib:
            miss = [i for i in ia if i not in ib]; add = [i for i in ib if i not in ia]
            errors.append(f"paragraph structure differs — missing {miss[:6]}, unexpected {add[:6]}")
            # ids shifted, so a paragraph-by-paragraph comparison would only
            # cascade noise: report what is missing by clause marker instead.
            oe, ow = compare(src_path, tr_path, strict=False)
            return errors + oe, ow
        bb = {x["id"]: x for x in b}
        for x in a:
            y = bb.get(x["id"])
            if not y:
                continue
            if x["prefix"] != y["prefix"]:
                errors.append(f"{x['id']}: clause marker {x['prefix']!r} became {y['prefix']!r}")
            if x["tokens"] != y["tokens"]:
                errors.append(f"{x['id']}: footnote/image placeholders differ")
            if x["numbers"] != y["numbers"]:
                warnings.append(f"{x['id']}: numbers {x['numbers']} vs {y['numbers']}")
            if x["bold"] != y["bold"]:
                warnings.append(f"{x['id']}: bold segments {x['bold']} vs {y['bold']}")
            if x["words"] >= 6 and y["words"] < x["words"] * 0.4:
                warnings.append(f"{x['id']}: translation is much shorter ({y['words']} vs {x['words']} words)")
    else:
        ma = [x["prefix"] for x in a if x["prefix"]]
        mb = [x["prefix"] for x in b if x["prefix"]]
        import difflib
        sm = difflib.SequenceMatcher(None, ma, mb, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "delete":
                errors.append(f"clause marker(s) {ma[i1:i2][:6]} are in the source but missing in the translation")
            elif tag == "insert":
                warnings.append(f"extra clause marker(s) {mb[j1:j2][:6]} in the translation")
            elif tag == "replace":
                errors.append(f"clause markers {ma[i1:i2][:6]} differ from {mb[j1:j2][:6]}")
        if len(a) and abs(len(b) - len(a)) > max(3, 0.1 * len(a)):
            warnings.append(f"{len(b)} translatable paragraphs vs {len(a)} in the source")
    return errors, warnings


def cmd_verify(args):
    errors, warnings = compare(args.source, args.translation, strict=not args.outline)
    for w in warnings[:40]:
        print("warn :", w)
    for e in errors[:40]:
        print("ERROR:", e)
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract"); e.add_argument("source"); e.add_argument("-o", "--output", required=True)
    e.add_argument("--language", help="target language name (recorded in the JSON)")
    e.add_argument("--reuse", nargs=2, metavar=("OLD_EN_DOCX", "OLD_TRANSLATED_DOCX"),
                   help="pre-fill paragraphs whose English is unchanged from an earlier translation")
    e.set_defaults(fn=cmd_extract)
    a = sub.add_parser("apply"); a.add_argument("source"); a.add_argument("translations", nargs="+")
    a.add_argument("-o", "--output", required=True); a.add_argument("--allow-missing", action="store_true")
    a.add_argument("--force", action="store_true"); a.set_defaults(fn=cmd_apply)
    v = sub.add_parser("verify"); v.add_argument("source"); v.add_argument("translation")
    v.add_argument("--outline", action="store_true",
                   help="only compare clause markers (for a separately authored translated Word file)")
    v.set_defaults(fn=cmd_verify)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
