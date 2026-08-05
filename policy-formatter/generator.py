"""
Render a Policy content model to a BioMar-branded A4 PDF.

Layout (cover + flowing content pages with running header/footer/logo) is a
faithful reconstruction of the InDesign template. Type scale, colours,
margins and the cover artwork all come from `brand.py` / `assets/`.
"""
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame,
                                Paragraph, Spacer, Table, TableStyle,
                                NextPageTemplate, PageBreak, KeepTogether, Flowable)
from reportlab.platypus.flowables import HRFlowable, BalancedColumns
from xml.sax.saxutils import escape
import re

import brand as B
from model import Heading, Body, Bullet, TableBlock, ImageBlock, Columns
from reportlab.platypus import Image as RLImage
from io import BytesIO

B.register_fonts()

# ReportLab's Paragraph `bulletText` normally nudges the first line rightward
# whenever the bullet's own rendered width (+ a small safety pad) would run
# past `leftIndent` — meant to stop a wide bullet glyph from overlapping the
# text. Our numbered clauses use bulletText as a fixed tab stop for the clause
# number (see _set_clause_indent), and a handful of deeply-nested numbers
# ("4.3.4.1") are wide enough to trip that guard, which would shift only
# their first line and reproduce the exact first-line-vs-wrapped-line
# misalignment this mechanism exists to prevent. The official reference PDF
# has no such guard — a wide number simply sits close to the text with no
# push — so disable it: keep ReportLab's bullet drawing but always keep the
# body text at its normal (unshifted) position.
import reportlab.platypus.paragraph as _rl_paragraph
_rl_draw_bullet = _rl_paragraph._drawBullet
def _draw_bullet_no_overflow_shift(canvas, offset, cur_y, bulletText, style, rtl):
    _rl_draw_bullet(canvas, offset, cur_y, bulletText, style, rtl)
    return offset
_rl_paragraph._drawBullet = _draw_bullet_no_overflow_shift


# --------------------------------------------------------------------------
# Paragraph stylesheet (mirrors the IDML "Title / Subtitle / Body / Bullets")
# --------------------------------------------------------------------------
# Spacing values mirror the measured template grid (body leading 16, paragraph
# gap 11.4, and the heading spacing reproduced from the IDML Title/Subtitle).
# keepWithNext keeps a heading on the same page as the text that follows it,
# so a heading is never left orphaned at the bottom of a page.
H1 = ParagraphStyle("H1", fontName=B.F_DEMI, fontSize=14, leading=16,
                    textColor=B.BIOMAR_BLUE, spaceBefore=14.5, spaceAfter=15,
                    keepWithNext=1)
H2 = ParagraphStyle("H2", fontName=B.F_DEMI, fontSize=12, leading=14,
                    textColor=B.BIOMAR_BLUE, spaceBefore=5.3, spaceAfter=6.2,
                    keepWithNext=1)
H1_HANG, H2_HANG = H1, H2   # overridden per-policy by _set_clause_indent
BODY = ParagraphStyle("Body", fontName=B.F_REGULAR, fontSize=11, leading=16,
                      textColor=B.BIOMAR_BLUE, alignment=TA_JUSTIFY, spaceAfter=11.4,
                      splitLongWords=0, hyphenationLang="",
                      allowWidows=0, allowOrphans=0)
BODY_LEFT = ParagraphStyle("BodyLeft", parent=BODY, alignment=TA_LEFT)
BODY_BOLD = ParagraphStyle("BodyBold", parent=BODY, fontName=B.F_DEMI)
BODY_ITALIC = ParagraphStyle("BodyItalic", parent=BODY, fontName=B.F_ITALIC, alignment=TA_LEFT)
BODY_HANG, BODY_HANG_LEFT = BODY, BODY_LEFT   # overridden per-policy by _set_clause_indent
BODY_INDENT, BODY_INDENT_LEFT = BODY, BODY_LEFT   # overridden per-policy by _set_clause_indent
# Document title repeated as a lead heading on the first content page (some
# originals, e.g. the Code of Conduct, open the body with the title in large bold).
LEAD_TITLE = ParagraphStyle("LeadTitle", fontName=B.F_BOLD, fontSize=19, leading=22,
                            textColor=B.BIOMAR_BLUE, spaceAfter=11, spaceBefore=0)
BULLET = ParagraphStyle("Bullet", parent=BODY, alignment=TA_LEFT,
                        leftIndent=16, bulletIndent=2, spaceAfter=6)
BULLET_HANG = BULLET   # overridden per-policy by _set_clause_indent (lettered items, e.g. "a. ...")
# Two-column running text is set at the original's denser 10pt so each section
# keeps the same footprint as the official PDF (one page per 2-column section).
COL_BODY = ParagraphStyle("ColBody", parent=BODY_LEFT, fontSize=10, leading=13,
                          spaceAfter=8)
COL_BULLET = ParagraphStyle("ColBullet", parent=COL_BODY, alignment=TA_LEFT,
                            leftIndent=14, bulletIndent=2, spaceAfter=5)
COL_BODY_BOLD = ParagraphStyle("ColBodyBold", parent=COL_BODY, fontName=B.F_DEMI)
COL_FOOTNOTE = ParagraphStyle("ColFootnote", fontName=B.F_REGULAR, fontSize=7, leading=9,
                              textColor=B.BIOMAR_BLUE, alignment=TA_LEFT,
                              spaceBefore=6, spaceAfter=2)
CELL = ParagraphStyle("Cell", fontName=B.F_REGULAR, fontSize=8.5, leading=11,
                      textColor=B.BIOMAR_BLUE, splitLongWords=0, hyphenationLang="")
CELL_H = ParagraphStyle("CellH", parent=CELL, fontName=B.F_DEMI,
                        textColor=B.WHITE, alignment=TA_CENTER)        # column header
CELL_SEC = ParagraphStyle("CellSec", parent=CELL, fontName=B.F_DEMI,
                          textColor=B.WHITE)                            # section band row
CELL_C = ParagraphStyle("CellC", parent=CELL, alignment=TA_CENTER)     # short marks (√, —)
CELL_BULLET = ParagraphStyle("CellBullet", parent=CELL, leftIndent=10,
                             firstLineIndent=-8, spaceBefore=1.5)        # in-cell bullet
CELL_GAP = ParagraphStyle("CellGap", parent=CELL, spaceBefore=3.5)      # paragraph gap in a cell


_NUM = re.compile(r"^(\d+(?:\.\d+)*\.?)(\s+)(.*)$", re.S)
_LONG = re.compile(r"\S{28,}")
# A list item already lettered ("a. …", "b) …", "(a) …") carries its own marker,
# so it is rendered as an indented item WITHOUT a bullet glyph (the letter is the
# marker) — avoids the redundant "• a." double marking.
_LETTERED = re.compile(r"^\(?[a-z][.)]\s")
_LETTERED_SPLIT = re.compile(r"^(\(?[a-z][.)])\s+(.*)$", re.S)


def _breakable(t):
    """Insert zero-width break points inside very long tokens (URLs, paths) so
    they wrap inside a narrow column instead of overflowing and overlapping the
    next column. Break after path separators to keep the URL readable."""
    return _LONG.sub(lambda m: re.sub(r"([/?&])", "\\1​", m.group(0)), t)


def _fmt(text, number=True, widow=True, lstrip=True, rstrip=True):
    """Format clause text: (1) keep the last two words together so a paragraph
    never ends with a single orphaned word; (2) render a leading clause number
    (e.g. '2.3.2') in Demi. Headings are already fully Demi, so this is used
    for body/bullets/cells only. lstrip/rstrip=False preserve boundary
    whitespace — needed when formatting one run of a multi-run paragraph
    (_body_markup): trimming each segment on BOTH sides would eat the space
    between a bold run-in label and the text that follows it, so only the
    outer edge of the first/last run is trimmed, not the seam between runs."""
    t = text
    if lstrip:
        t = t.lstrip()
    if rstrip:
        t = t.rstrip()
    t = _breakable(t)
    if widow:
        parts = t.rsplit(" ", 1)
        if len(parts) == 2:
            t = parts[0] + " " + parts[1]   # glue last two words (no widow)
    m = _NUM.match(t) if number else None
    if m:
        return (f'<font name="{B.F_DEMI}">{escape(m.group(1))}</font>'
                f'{m.group(2)}{escape(m.group(3))}')
    return escape(t)


def _body_markup(b):
    """Markup for a Body block, wrapping any run-in bold/italic segment in the
    brand's Demi/Italic face. Uses explicit <font name="Brand-Demi"/"Brand-
    Italic"> tags rather than <b>/<i> — ReportLab's <b>/<i> only resolve to a
    styled face via a registered font family (registerFontFamily), which this
    pipeline never sets up; every other styled spot in this file (clause
    numbers, table headers) already uses <font name=...> for the same reason.
    A run that is both bold and italic renders bold — there is no bundled
    bold-italic face to combine the two."""
    runs = getattr(b, "runs", None)
    if not runs:
        return _fmt(b.text)
    n = len(runs)
    out = []
    for i, (t, bd, it) in enumerate(runs):
        seg = _fmt(t, number=(i == 0), widow=(i == n - 1),
                   lstrip=(i == 0), rstrip=(i == n - 1))
        if bd:
            seg = f'<font name="{B.F_DEMI}">{seg}</font>'
        elif it:
            seg = f'<font name="{B.F_ITALIC}">{seg}</font>'
        out.append(seg)
    return "".join(out)


def _band(r):
    """A full-width row whose non-empty cells are all identical (a merged
    title/section row), e.g. 'Table 1: ...' or '2. The general meeting'."""
    f = [c for c in r if c.strip()]
    return len(set(f)) == 1 and len(f) > 1


_BASE_TSTYLE = [
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
]


def _column_widths(rows, ncols, hdr):
    """Proportional to content, never narrower than a column's longest word
    (so 'Complies' never wraps), and with columns under a 2-level header span
    made equal width (so 'Why' and 'How' match)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    avail, PAD = B.PAGE_W - B.MARGIN_L - B.MARGIN_R, 16
    body = [r for r in rows if not _band(r)] or rows
    colmax = [max(max((len(r[c]) for r in body), default=1), 5) for c in range(ncols)]
    tot = sum(colmax)
    minw = [PAD + max((stringWidth(w, B.F_DEMI, 8.5)
                       for r in rows for w in r[c].split()), default=10)
            for c in range(ncols)]
    colw = [max(avail * colmax[c] / tot, minw[c]) for c in range(ncols)]
    over = sum(colw) - avail
    if over > 0:
        slack = [colw[c] - minw[c] for c in range(ncols)]
        ts = sum(slack)
        colw = ([colw[c] - over * slack[c] / ts for c in range(ncols)] if ts > 0
                else [w * avail / sum(colw) for w in colw])
    if hdr == 2:                                  # equalise sub-columns of a span
        h0 = rows[0]
        c = 0
        while c < ncols:
            j = c
            while j + 1 < ncols and h0[j + 1] and h0[j + 1] == h0[c]:
                j += 1
            if j > c:
                eq = sum(colw[c:j + 1]) / (j - c + 1)
                for k in range(c, j + 1):
                    colw[k] = eq
            c = j + 1
    return colw


def _header_rows(rows, ncols, hdr):
    """Build the (1- or 2-row) header cell data and its span/background style
    commands (row-relative)."""
    if hdr == 0:
        return [], []
    style = []
    if hdr == 1:
        style.append(("BACKGROUND", (0, 0), (-1, 0), B.BIOMAR_BLUE))
        return [[Paragraph(escape(c), CELL_H) for c in rows[0]]], style
    h0, h1 = list(rows[0]), list(rows[1])
    for c in range(ncols):                            # vertical spans
        if h0[c] and h0[c] == h1[c]:
            style.append(("SPAN", (c, 0), (c, 1)))
            h1[c] = ""
    c = 0
    while c < ncols:                                  # horizontal spans in row 0
        j = c
        while j + 1 < ncols and h0[j + 1] and h0[j + 1] == h0[c]:
            j += 1
        if j > c:
            style.append(("SPAN", (c, 0), (j, 0)))
            for k in range(c + 1, j + 1):
                h0[k] = ""
        c = j + 1
    style += [("BACKGROUND", (0, 0), (-1, 1), B.BIOMAR_BLUE),
              ("VALIGN", (0, 0), (-1, 1), "MIDDLE")]
    return ([[Paragraph(escape(x), CELL_H) if x else "" for x in h0],
             [Paragraph(escape(x), CELL_H) if x else "" for x in h1]], style)


_REC = re.compile(r"(The [Cc]ommittee recommends)")
def _bold_rec(markup):
    """Render 'The Committee recommends' in Demi (bold) inside recommendation cells
    — but only the FIRST occurrence within a paragraph (count=1); repeated mentions
    in the same paragraph stay in the regular weight."""
    return _REC.sub(rf'<font name="{B.F_DEMI}">\1</font>', markup, count=1)


def _cell_flowables(c):
    """A multi-paragraph cell: first line keeps its clause number, '• ' lines
    become hanging bullets, other lines are spaced continuation paragraphs.
    "The Committee recommends" is only bolded on the cell's FIRST line — a
    repeat of the phrase on a later paragraph within the same cell (e.g. a
    follow-up sentence starting "The Committee recommends...") stays regular
    weight, since count=1 inside _bold_rec only dedupes within one line."""
    out = []
    for i, line in enumerate([ln.strip() for ln in c.split("\n") if ln.strip()]):
        rec = _bold_rec if i == 0 else (lambda m: m)
        if line.startswith("• "):
            out.append(Paragraph("•&nbsp;&nbsp;" + rec(_fmt(line[2:], number=False, widow=False)), CELL_BULLET))
        else:
            out.append(Paragraph(rec(_fmt(line, number=(i == 0), widow=False)),
                                  CELL if i == 0 else CELL_GAP))
    return out


def _body_cells(r, ncols):
    """Return (cells, is_band) for one body row."""
    if _band(r):
        txt = [c for c in r if c.strip()][0]
        return [Paragraph(escape(txt), CELL_SEC)] + [""] * (ncols - 1), True
    cells = []
    for c in r:
        s = c.strip()
        if len(s) <= 2:
            cells.append(Paragraph(escape(c), CELL_C) if s else "")
        elif "\n" in c:
            cells.append(_cell_flowables(c))
        else:
            cells.append(Paragraph(_bold_rec(_fmt(c, widow=False)), CELL))
    return cells, False


def _assemble(head_data, head_style, body_rows, colw, ncols, repeat,
              span_cols=frozenset()):
    """Build one Table from the header + a set of body rows, with bands, zebra
    striping and a grid. Column separators are drawn continuously (top to
    bottom, through the full-width section bands too) so the column structure
    stays readable; horizontal separators are drawn per row."""
    data = list(head_data)
    style = list(_BASE_TSTYLE) + list(head_style)
    hdr = len(head_data)
    zebra = 0
    for r in body_rows:
        i = len(data)
        cells, band = _body_cells(r, ncols)
        data.append(cells)
        if band:
            style += [("SPAN", (0, i), (-1, i)),
                      ("BACKGROUND", (0, i), (-1, i), B.OCEAN_BLUE)]
            zebra = 0
        else:
            if zebra % 2:
                style.append(("BACKGROUND", (0, i), (-1, i), B.TABLE_STRIPE))
            zebra += 1
    # Vertical separators: continuous over the whole height. A boundary that
    # sits under a header span (e.g. Why|How under "Explains") starts at row 1.
    for c in range(ncols - 1):
        r0 = 1 if c in span_cols else 0
        style.append(("LINEAFTER", (c, r0), (c, -1), 0.5, B.TABLE_GRID))
    # Horizontal line under a row-0 span header (e.g. under "Explains",
    # separating it from "Why"/"How").
    for c in span_cols:
        style.append(("LINEBELOW", (c, 0), (c + 1, 0), 0.5, B.TABLE_GRID))
    style += [("LINEBELOW", (0, hdr - 1), (-1, -1), 0.5, B.TABLE_GRID),
              ("BOX", (0, 0), (-1, -1), 0.7, B.TABLE_GRID)]
    t = Table(data, colWidths=colw, repeatRows=hdr if repeat else 0)
    t.setStyle(TableStyle(style))
    return t


def _row_height(cells, colw):
    t = Table([cells], colWidths=colw)
    t.setStyle(TableStyle(_BASE_TSTYLE))
    return t.wrap(sum(colw), 100000)[1]


_SIG_LABELS = ("company", "name", "position", "date", "place", "signature")


def _is_signature_form(block):
    """A small form whose left column is labels ending in ':' (Company:, Date:,
    Signature: …) — drawn as the official light-blue declaration box."""
    rows = block.rows
    if not (2 <= len(rows) <= 8):
        return False
    labels = [(_first(r) or "").strip().lower() for r in rows]
    if not all(l.endswith(":") for l in labels if l):
        return False
    hits = sum(any(k in l for k in _SIG_LABELS) for l in labels)
    return hits >= 3


def _first(row):
    return row[0] if row else ""


_SIG_TEAL = colors.Color(0.729, 0.898, 0.957)   # #bae5f3 bands / cell borders


class SignatureBox(Flowable):
    """The supplier declaration box, drawn to match the official PDF: a rounded
    white card with a teal band top and bottom, thin teal cell borders and the
    field labels (navy) sitting at the bottom-left of each cell with writing
    space above. 'Date:' and 'Place:' share a split row."""
    def __init__(self, width, rows, band=20, row_h=42, radius=11):
        Flowable.__init__(self)
        self.width = width
        self.rows = rows
        self.band = band
        self.row_h = row_h
        self.radius = radius
        self.height = band * 2 + row_h * len(rows)

    def wrap(self, availW, availH):
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        w, h, r, bd = self.width, self.height, self.radius, 0.8
        top = h - self.band
        # teal rounded base, then a white middle that leaves the two bands and
        # thin side borders showing through.
        c.setFillColor(_SIG_TEAL)
        c.roundRect(0, 0, w, h, r, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.rect(bd, self.band, w - 2 * bd, h - 2 * self.band, stroke=0, fill=1)
        # horizontal cell borders
        c.setStrokeColor(_SIG_TEAL)
        c.setLineWidth(0.8)
        for k in range(len(self.rows) + 1):
            y = top - k * self.row_h
            c.line(bd, y, w - bd, y)
        # vertical divider for the split (Date | Place) row
        split = w * 0.55
        for i, (_l, rt) in enumerate(self.rows):
            if rt:
                cell_top = top - i * self.row_h
                c.line(split, cell_top - self.row_h, split, cell_top)
        # labels: navy, bottom-left of each cell, writing space above
        c.setFillColor(B.BIOMAR_BLUE)
        c.setFont(B.F_DEMI, 11)
        for i, (l, rt) in enumerate(self.rows):
            cell_bot = top - (i + 1) * self.row_h
            c.drawString(15, cell_bot + 12, l)
            if rt:
                c.drawString(split + 15, cell_bot + 12, rt)


def _signature_card_flowables(block):
    """Build the declaration box from the imported form rows."""
    rows = []
    for r in block.rows:
        left = (r[0] if len(r) > 0 else "").strip()
        right = (r[1] if len(r) > 1 else "").strip()
        rows.append((left, right or None))
    box = SignatureBox(_CONTENT_W, rows)
    return [Spacer(1, 10), KeepTogether([box]), Spacer(1, 8)]


def _table_flowables(block):
    """Return the flowables for a table. Small tables are a single Table; large
    tables are paginated manually so the header repeats and a page never ends
    on a section band (which would orphan it from its rows)."""
    ncols = max(len(r) for r in block.rows)
    rows = [list(r) + [""] * (ncols - len(r)) for r in block.rows]
    hdr = 0
    if block.header and rows and not _band(rows[0]):
        hdr = 1
        if (len(rows) > 1 and not _band(rows[1]) and
                (any(rows[0][c] and rows[0][c] == rows[0][c + 1] for c in range(ncols - 1))
                 or any(rows[0][c] and rows[0][c] == rows[1][c] for c in range(ncols)))):
            hdr = 2
    colw = _column_widths(rows, ncols, hdr)
    head_data, head_style = _header_rows(rows, ncols, hdr)
    # Column boundaries that sit under a row-0 horizontal span (e.g. Why|How
    # under "Explains"): their vertical separator must start below the span.
    span_cols = set()
    if hdr == 2:
        h0 = rows[0]
        span_cols = {c for c in range(ncols - 1) if h0[c] and h0[c] == h0[c + 1]}
    body = rows[hdr:]

    if len(body) <= 12:                                # fits a page -> one table
        return [_assemble(head_data, head_style, body, colw, ncols, block.header,
                          span_cols)]

    # Manual pagination on its own pages.
    head_h = _row_height([c if c else "" for c in (head_data[0] if head_data else [])],
                         colw) if head_data else 0
    if hdr == 2:
        head_h += _row_height([c if c else "" for c in head_data[1]], colw)
    page_h = B.PAGE_H - B.MARGIN_TOP_CONT - B.MARGIN_BOTTOM - head_h - 18
    heights = [_row_height(_body_cells(r, ncols)[0], colw) for r in body]

    chunks, i = [], 0
    while i < len(body):
        cur, h = [], 0.0
        while i < len(body) and (not cur or h + heights[i] <= page_h):
            cur.append(i); h += heights[i]; i += 1
        while len(cur) > 1 and _band(body[cur[-1]]):   # don't orphan trailing bands
            i = cur.pop()
        chunks.append(cur)

    flow = [PageBreak()]
    for ci, ch in enumerate(chunks):
        flow.append(_assemble(head_data, head_style, [body[j] for j in ch],
                              colw, ncols, block.header, span_cols))
        if ci < len(chunks) - 1:
            flow.append(PageBreak())
    return flow


_CONTENT_W = B.PAGE_W - B.MARGIN_L - B.MARGIN_R


def _image_flowables(b):
    """Render an embedded image, scaled to fit the content width."""
    try:
        img = RLImage(BytesIO(b.data))
    except Exception:
        return []
    iw, ih = float(img.imageWidth or 1), float(img.imageHeight or 1)
    max_h = B.PAGE_H - B.MARGIN_TOP_CONT - B.MARGIN_BOTTOM - 12   # fit one content frame
    w = b.width or iw
    if w > _CONTENT_W:
        w = _CONTENT_W
    h = ih * (w / iw)
    if h > max_h:                       # very tall image -> scale by height
        h = max_h
        w = iw * (h / ih)
    img.drawWidth = w
    img.drawHeight = h
    img.hAlign = "CENTER"
    return [Spacer(1, 5), img, Spacer(1, 7)]


def _col_flowables(blocks):
    out = []
    for sb in blocks:
        if isinstance(sb, Heading):
            out.append(Paragraph(escape(sb.text), H1 if sb.level == 1 else H2))
        elif isinstance(sb, Bullet):
            if _LETTERED.match(sb.text.strip()):
                out.append(Paragraph(_fmt(sb.text), COL_BULLET))
            else:
                out.append(Paragraph(_fmt(sb.text), COL_BULLET, bulletText="•"))
        elif getattr(sb, "runs", None):
            out.append(Paragraph(_body_markup(sb), COL_BODY))
        elif getattr(sb, "bold", False):
            out.append(Paragraph(_fmt(sb.text), COL_BODY_BOLD))
        else:
            out.append(Paragraph(_fmt(sb.text), COL_BODY))
    return out


def _flow_height(f, w):
    try:
        h = f.wrap(w, 100000)[1]
    except Exception:
        return 0.0
    sb = f.getSpaceBefore() if hasattr(f, "getSpaceBefore") else 0
    sa = f.getSpaceAfter() if hasattr(f, "getSpaceAfter") else 0
    return h + sb + sa


def _is_col_heading(f):
    return getattr(f, "style", None) is not None and f.style.name in ("H1", "H2")


def _is_footnote(text):
    return text.lstrip()[:1] in "¹²³⁴⁵⁶⁷⁸⁹"


def _columns_flowables(b):
    """Render two text columns newspaper-style and balanced: the content flows
    in reading order (left column top-to-bottom, then right) and BalancedColumns
    splits it so both columns end at the same height — matching the original,
    instead of one column finishing early with a white gap."""
    # Pull out small footnotes (¹ ², …) so they render small at the foot of the
    # page instead of inline in a column.
    foot = []
    src = []
    for c in b.cols:
        keep = []
        for sb in c:
            if isinstance(sb, Body) and _is_footnote(sb.text):
                foot.append(sb)
            else:
                keep.append(sb)
        src.append(keep)
    foot_flow = [Paragraph(_fmt(f.text), COL_FOOTNOTE) for f in foot]

    cols = [c for c in src if c]
    if not cols:
        return foot_flow
    if len(cols) == 1:
        return _col_flowables(cols[0]) + foot_flow
    flow = _col_flowables(cols[0]) + _col_flowables(cols[1])
    gutter = 16
    colw = (_CONTENT_W - gutter) / 2          # text width of each column
    heights = [_flow_height(f, colw) for f in flow]
    # Usable column height on a content page, with headroom for measurement
    # slack so a non-splitting column never overflows the frame.
    col_h = B.PAGE_H - B.MARGIN_TOP_CONT - B.MARGIN_BOTTOM - 18
    foot_h = sum(_flow_height(f, _CONTENT_W) for f in foot_flow)
    budget = col_h - 28 - foot_h

    def _table(items):
        # Balance one page-worth of items into two columns by choosing the split
        # that minimises the taller column, so both end about level and neither
        # overflows; the table never splits, keeping the reading order intact.
        if len(items) == 1:
            left, right = items, []
        else:
            best_sp, best_max = 1, float("inf")
            for sp in range(1, len(items)):
                l = sum(heights[j] for j in items[:sp])
                rr = sum(heights[j] for j in items[sp:])
                m = max(l, rr)
                if m < best_max:
                    best_max, best_sp = m, sp
            sp = best_sp
            while sp > 1 and _is_col_heading(flow[items[sp - 1]]):
                sp -= 1
            left = items[:sp]
            right = items[sp:]
        t = Table([[[flow[j] for j in left], [flow[j] for j in right]]],
                  colWidths=[colw + gutter / 2, colw + gutter / 2])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), gutter / 2),
            ("LEFTPADDING", (1, 0), (1, -1), gutter / 2),
            ("RIGHTPADDING", (1, 0), (1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    # Paginate the reading-order flow into page-sized chunks; each chunk is a
    # self-contained balanced 2-column block (a page break separates chunks so
    # the left/right columns of one page always read together, in order). The
    # chunk fills up to two columns (2*budget) before breaking.
    out, i, n, first = [], 0, len(flow), True
    while i < n:
        chunk, acc = [], 0.0
        while i < n and (not chunk or acc + heights[i] <= 2 * budget):
            chunk.append(i)
            acc += heights[i]
            i += 1
        if not first:
            out.append(PageBreak())
        out.append(_table(chunk))
        first = False
    # Push the footnotes down so they sit at the foot of the last page, like the
    # original, instead of right under the (possibly short) last column.
    if foot_flow:
        try:
            last_h = out[-1].wrap(_CONTENT_W, col_h)[1]
        except Exception:
            last_h = budget
        gap = col_h - last_h - foot_h - 8
        if gap > 6:
            foot_flow = [Spacer(1, gap)] + foot_flow
    return [Spacer(1, 4)] + out + [Spacer(1, 6)] + foot_flow


def _story(policy):
    flow = []
    # Some originals repeat the document title as a large bold lead on the first
    # content page (e.g. the Code of Conduct); opt in per policy.
    if getattr(policy, "lead_title", False):
        flow.append(Paragraph(escape(policy.title), LEAD_TITLE))
    # A supplier declaration (intro text + signature box) sits on its own page in
    # the original, with the content after it starting fresh. Break around it.
    blocks = policy.blocks
    sig_i = next((i for i, b in enumerate(blocks)
                  if isinstance(b, TableBlock) and _is_signature_form(b)), None)
    dec_i = None
    if sig_i is not None:
        j = sig_i - 1
        while j >= 0 and isinstance(blocks[j], Body):
            j -= 1
        dec_i = j + 1
    # Tracks whether the previous block was a numbered sub-heading run in
    # (e.g. "3.2 Incentive pay" bold, or "4.3.5.4 Cash-based..." italic) with
    # no clause number of its own — the following un-numbered paragraph is
    # that sub-heading's actual content and must hang-indent to match it,
    # or the page reads as misaligned ("straight lines" the original keeps).
    prev_subhead = False
    for i, b in enumerate(blocks):
        if i == dec_i:
            flow.append(PageBreak())
        if isinstance(b, Heading):
            # A hanging_indent policy tab-aligns the heading title to the same
            # column as its clause text below ("1  Name and objects" / "1.1
            # The Company's name..." both start their text at `indent`) — per
            # Marianne's reference layout. Other policies keep the number
            # embedded inline with a plain space: without the rest of the
            # article-style hang-indent system around it, tab-aligning a lone
            # heading number would just leave "1" and "Introduction" with an
            # oddly large, out-of-place gap between them.
            style = H1 if b.level == 1 else H2
            m = _NUM.match(b.text.strip()) if getattr(policy, "hanging_indent", False) else None
            if m:
                hstyle = H1_HANG if b.level == 1 else H2_HANG
                flow.append(Paragraph(escape(m.group(3)), hstyle, bulletText=m.group(1)))
            else:
                flow.append(Paragraph(escape(b.text), style))
            # An un-numbered paragraph right after a top-level heading ("3
            # Remuneration of the members of the Board of Directors" / "The
            # remuneration offered to...") is that section's lead-in text, not
            # a fresh flush-left block — it needs the same indent as the rest
            # of the hanging-indent layout. A numbered clause right after the
            # heading overrides this via is_numbered_subhead below regardless.
            prev_subhead = bool(getattr(policy, "hanging_indent", False))
        elif isinstance(b, Body):
            # Justify normal running text; left-align short lines and anything
            # with a URL/long token so justification doesn't stretch the spaces.
            justify = len(b.text) >= 90 and "://" not in b.text
            is_numbered_subhead = bool(_NUM.match(b.text.strip()))
            if getattr(b, "runs", None):
                flow.append(Paragraph(_body_markup(b), BODY if justify else BODY_LEFT))
                prev_subhead = False
            elif getattr(b, "italic", False):
                # Whole-line italic sub-heading: keep the leading number inline
                # (no bold) and set the entire line in the oblique face.
                flow.append(Paragraph(_fmt(b.text, number=False), BODY_ITALIC))
                prev_subhead = is_numbered_subhead
            elif getattr(b, "bold", False):
                flow.append(Paragraph(_fmt(b.text), BODY_BOLD))
                prev_subhead = is_numbered_subhead
            else:
                # A numbered clause ("1.1 The Company's...") hang-indents (when
                # the policy opts in) so wrapped lines align under the clause
                # text. The paragraph right after a numbered sub-heading (its
                # content, just split into a separate block, e.g. "3.2 Incentive
                # pay" / "The Board of Directors shall not...") has no number of
                # its own to occupy the negative first-line indent, so it needs a
                # UNIFORM indent instead — otherwise a short paragraph that never
                # wraps would sit flush at the margin, out of line with the rest.
                # Anything else uses the plain style.
                if is_numbered_subhead:
                    style = BODY_HANG if justify else BODY_HANG_LEFT
                    if getattr(policy, "hanging_indent", False):
                        m = _NUM.match(b.text.strip())
                        flow.append(Paragraph(_fmt(m.group(3), number=False), style, bulletText=m.group(1)))
                    else:
                        flow.append(Paragraph(_fmt(b.text), style))
                elif prev_subhead:
                    style = BODY_INDENT if justify else BODY_INDENT_LEFT
                    flow.append(Paragraph(_fmt(b.text), style))
                else:
                    style = BODY if justify else BODY_LEFT
                    flow.append(Paragraph(_fmt(b.text), style))
                if is_numbered_subhead:
                    # A numbered-but-not-bold block can still be a short
                    # sub-heading in the source ("3.2 Incentive pay", no
                    # trailing period) rather than a full clause ("1.1 The
                    # Company's name is ... A/S.") — only the former's content
                    # needs the uniform-indent style.
                    stripped = b.text.strip()
                    prev_subhead = (len(stripped.split()) <= 8
                                    and not stripped.rstrip().endswith((".", ":", ";")))
                # else: leave prev_subhead as-is — a sub-heading's content can
                # span several paragraphs, all of which need the same indent.
        elif isinstance(b, Bullet):
            prev_subhead = False
            if _LETTERED.match(b.text.strip()) and getattr(policy, "hanging_indent", False):
                lm = _LETTERED_SPLIT.match(b.text.strip())
                flow.append(Paragraph(_fmt(lm.group(2), number=False), BULLET_HANG,
                                      bulletText=lm.group(1)))     # letter is the marker
            elif _LETTERED.match(b.text.strip()):
                flow.append(Paragraph(_fmt(b.text), BULLET_HANG))     # letter is the marker (no hang)
            else:
                flow.append(Paragraph(_fmt(b.text), BULLET, bulletText="•"))
        elif isinstance(b, TableBlock):
            prev_subhead = False
            if _is_signature_form(b):
                flow.extend(_signature_card_flowables(b))
            else:
                flow.append(Spacer(1, 4))
                flow.extend(_table_flowables(b))
                flow.append(Spacer(1, 8))
        elif isinstance(b, ImageBlock):
            prev_subhead = False
            flow.extend(_image_flowables(b))
        elif isinstance(b, Columns):
            prev_subhead = False
            flow.extend(_columns_flowables(b))
        if i == sig_i:
            flow.append(PageBreak())     # definitions/refs start on the next page
    return flow


# --------------------------------------------------------------------------
# Page furniture
# --------------------------------------------------------------------------
def _draw_cover(c, doc):
    policy = doc._policy
    # The official empty cover already has the navy pellet artwork, the logo
    # and the decorative rule baked in; we only add the year, title and address.
    # Guidelines use the same artwork recoloured to ocean blue (#0471ad) so
    # they read as visually distinct from policies on the shelf.
    bg = B.COVER_BG_GUIDELINE if getattr(policy, "category", "Policy") == "Guideline" else B.COVER_BG
    c.drawImage(ImageReader(bg), 0, 0, B.PAGE_W, B.PAGE_H,
                preserveAspectRatio=False, mask=None)

    # Title - auto-fit width, wrap; anchored so the bottom line sits just above
    # the baked rule, with the year stacked above it.
    avail = B.PAGE_W - B.MARGIN_L - 30
    # Covers that carry a year stack a big title above it; year-less covers
    # (e.g. the Code of Conduct) use the original's smaller 44pt title instead.
    start = 70 if getattr(policy, "cover_year", True) else 44
    size, lines = _fit_title(c, policy.title, avail, start)
    n = len(lines)
    last_baseline = B.COVER_RULE_Y + 65.6    # bottom title line, matches template
    c.setFillColor(B.COVER_TITLE)
    c.setFont(B.F_BOLD, size)
    for i, ln in enumerate(lines):
        c.drawString(B.MARGIN_L, last_baseline + (n - 1 - i) * size * 1.02, ln)
    top_title = last_baseline + (n - 1) * size * 1.02

    # Year sits above the title block (some originals carry no year on the cover).
    if getattr(policy, "cover_year", True):
        c.setFillColor(B.COVER_YEAR)
        c.setFont(B.F_BOLD, 60)
        c.drawString(B.MARGIN_L, top_title + 84.3, policy.year)

    # Address block (bottom-left, below the rule)
    c.setFillColor(B.COVER_ADDR)
    ay = 205
    c.setFont(B.F_BOLD, 10)
    c.drawString(B.MARGIN_L, ay, B.ADDRESS_LINES[0])
    c.setFont(B.F_REGULAR, 10)
    for ln in B.ADDRESS_LINES[1:]:
        ay -= 18
        c.drawString(B.MARGIN_L, ay, ln)
    c.drawString(B.MARGIN_L, ay - 36, B.WEBSITE)


def _fit_title(c, title, avail, start):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words = title.split()
    for size in range(start, 23, -1):
        lines, cur = [], ""
        ok = True
        for w in words:
            if stringWidth(w, B.F_BOLD, size) > avail:
                ok = False
                break
            trial = (cur + " " + w).strip()
            if stringWidth(trial, B.F_BOLD, size) <= avail:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if ok and len(lines) <= 3:
            return size, lines
    return 24, [title]


def _draw_logo(c, path=B.LOGO):
    c.drawImage(ImageReader(path), B.LOGO_X, B.PAGE_H - B.LOGO_TOP - B.LOGO_H,
                B.LOGO_W, B.LOGO_H, preserveAspectRatio=True, mask="auto")


def _draw_content_furniture(c, doc):
    policy = doc._policy
    # Running header (top-left) - line gap 13 pt to match the template
    c.setFillColor(B.BIOMAR_BLUE)
    c.setFont(B.F_REGULAR, 8)
    c.drawString(B.MARGIN_L, B.PAGE_H - 47, B.COMPANY)
    c.drawString(B.MARGIN_L, B.PAGE_H - 47 - 13, policy.title)
    _draw_logo(c)
    # Footer (centred), with an optional small disclaimer line beneath it.
    c.setFont(B.F_REGULAR, 8)
    c.drawCentredString(B.PAGE_W / 2.0, 25, B.FOOTER)
    note = getattr(policy, "footer_note", "")
    if note:
        c.setFillColor(colors.Color(0.576, 0.584, 0.596))   # #939598 grey
        c.setFont(B.F_REGULAR, 6.5)
        c.drawCentredString(B.PAGE_W / 2.0, 14, note)
        c.setFillColor(B.BIOMAR_BLUE)


def _draw_back_cover(c, doc):
    policy = doc._policy
    # The official empty back cover already has the pellet artwork, the logo,
    # the tagline and the URL baked in; we only overlay the optional card.
    bg = B.COVER_BG_BACK_GUIDELINE if getattr(policy, "category", "Policy") == "Guideline" else B.COVER_BG_BACK
    c.drawImage(ImageReader(bg), 0, 0, B.PAGE_W, B.PAGE_H,
                preserveAspectRatio=False, mask=None)
    # The version-history / owner-approver card is shown on the signed copy and
    # on standalone documents. The unsigned copy of a signed/unsigned pair drops
    # it, so the two variants are distinguishable.
    show_card = policy.signatures or not getattr(policy, "has_signed", False)
    if show_card and any([policy.approval_date, policy.owner, policy.approver]):
        _draw_version_card(c, policy)


def _fill_round_rect(c, x, y, w, h, r):
    """Fill a rounded rectangle from axis-aligned rectangles + corner circles
    rather than one compound roundRect path. Chrome's embedded PDF viewer
    (PDFium) can mis-rasterise a single roundRect fill at certain zoom levels,
    leaving a diagonal navy wedge across the card; these primitives rasterise
    reliably. The visual result is identical."""
    c.rect(x + r, y, w - 2 * r, h, stroke=0, fill=1)
    c.rect(x, y + r, w, h - 2 * r, stroke=0, fill=1)
    for ccx, ccy in ((x + r, y + r), (x + w - r, y + r),
                     (x + r, y + h - r), (x + w - r, y + h - r)):
        c.circle(ccx, ccy, r, stroke=0, fill=1)


def _draw_version_card(c, policy):
    # White "Version history / Owner and approver" card, drawn on the back
    # cover only when approval data is supplied. Layout (column x-positions,
    # Light 8 pt labels/values, Demi 10 pt headers) matches the template card.
    cw, ch = 380.0, 100.0
    cx = (B.PAGE_W - cw) / 2.0          # page-centred, like the template
    cy = B.PAGE_H - 150 - ch
    right = cx + cw
    c.setFillColor(B.WHITE)
    _fill_round_rect(c, cx, cy, cw, ch, 10)

    # Absolute column geometry from the template card.
    L_LABEL_R, L_VALUE = 199.0, 201.5   # left column: label right-edge, value
    R_LABEL, R_VALUE = 266.8, 326.3     # right column: label, value
    DIVIDER = 255.0

    head_y = cy + ch - 24
    c.setFillColor(B.BIOMAR_BLUE)
    c.setFont(B.F_DEMI, 10)
    c.drawCentredString(193, head_y, "Version history")
    c.drawCentredString(364, head_y, "Owner and approver")
    c.setStrokeColor(B.LIGHT_RULE)
    c.setLineWidth(0.5)
    c.line(cx + 14, head_y - 10, right - 14, head_y - 10)   # under headers
    c.line(DIVIDER, cy + 10, DIVIDER, head_y - 10)          # column divider

    # Version line carries its date; the "Approval date" row is shown whenever
    # the policy has an approval date (both signed and unsigned variants).
    vdate = policy.approval_date or getattr(policy, "version_date", "") or "—"
    rows_l = [(policy.version, vdate)]
    if policy.approval_date:
        rows_l.append(("Approval date:", policy.approval_date))
    rows_r = [("Owner:", policy.owner or "—"),
              ("Approver:", policy.approver or "Executive Committee")]
    ry = head_y - 27
    for k in range(max(len(rows_l), len(rows_r))):
        c.setFillColor(B.BIOMAR_BLUE)
        c.setFont(B.F_LIGHT, 8)
        if k < len(rows_l):
            la, va = rows_l[k]
            c.drawRightString(L_LABEL_R, ry, la)
            c.drawString(L_VALUE, ry, va)
        if k < len(rows_r):
            lb, vb = rows_r[k]
            c.drawString(R_LABEL, ry, lb)
            # Shrink the owner/approver value if it would overflow the card.
            size, avail = 8.0, right - R_VALUE - 8
            while size > 6 and c.stringWidth(vb, B.F_LIGHT, size) > avail:
                size -= 0.5
            c.setFont(B.F_LIGHT, size)
            c.drawString(R_VALUE, ry, vb)
        c.setStrokeColor(B.LIGHT_RULE)
        c.line(cx + 14, ry - 9, right - 14, ry - 9)
        ry -= 25


def _draw_signatures(c, doc):
    policy = doc._policy
    _draw_content_furniture(c, doc)            # header + logo + footer

    # Adoption statement (centred, below the logo).
    if policy.adopted_on and policy.effective_on:
        text = (f"As adopted by the Board of Directors of BioMar Group "
                f"on {policy.adopted_on} to take effect from {policy.effective_on}.")
    else:
        text = "As adopted by the Board of Directors of BioMar Group."
    c.setFillColor(B.BIOMAR_BLUE)
    c.setFont(B.F_REGULAR, 11)
    cx = B.PAGE_W / 2.0
    _centred_wrapped(c, text, cx, B.PAGE_H - 175, B.PAGE_W - 230, 16)

    # Signature blocks: chair centred on top, then a two-column grid.
    def sig(x, y, name):
        c.setStrokeColor(B.BIOMAR_BLUE)
        c.setLineWidth(0.8)
        c.line(x - 95, y, x + 95, y)
        c.setFillColor(B.BIOMAR_BLUE)
        c.setFont(B.F_REGULAR, 11)
        c.drawCentredString(x, y - 22, name)

    left, right = B.MARGIN_L + 130, B.PAGE_W - B.MARGIN_R - 130
    sig(cx, B.PAGE_H - 365, B.BOARD_CHAIR)
    rows = [B.BOARD_MEMBERS[i:i + 2] for i in range(0, len(B.BOARD_MEMBERS), 2)]
    y = B.PAGE_H - 475
    for row in rows:
        xs = [left, right] if len(row) == 2 else [cx]
        for x, name in zip(xs, row):
            sig(x, y, name)
        y -= 110


def _centred_wrapped(c, text, cx, y, max_w, leading):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words, line, lines = text.split(), "", []
    for w in words:
        t = (line + " " + w).strip()
        if stringWidth(t, c._fontname, c._fontsize) <= max_w:
            line = t
        else:
            lines.append(line); line = w
    if line:
        lines.append(line)
    for ln in lines:
        c.drawCentredString(cx, y, ln)
        y -= leading


def _frame(top):
    return Frame(B.MARGIN_L, B.MARGIN_BOTTOM,
                 B.PAGE_W - B.MARGIN_L - B.MARGIN_R,
                 B.PAGE_H - top - B.MARGIN_BOTTOM,
                 leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)


def _set_body_size(size):
    """Rebuild the body/​bullet/​column paragraph styles for a given point size so
    a policy can match its original's density (e.g. the Code of Conduct is set at
    10pt, the rest at the default 11pt). Spacing and leading scale with the size."""
    global BODY, BODY_LEFT, BODY_BOLD, BODY_ITALIC, BULLET, COL_BODY, COL_BULLET, COL_BODY_BOLD
    BODY = ParagraphStyle("Body", fontName=B.F_REGULAR, fontSize=size,
                          leading=size * 16 / 11.0, textColor=B.BIOMAR_BLUE,
                          alignment=TA_JUSTIFY, spaceAfter=size * 11.4 / 11.0,
                          splitLongWords=0, hyphenationLang="",
                          allowWidows=0, allowOrphans=0)
    BODY_LEFT = ParagraphStyle("BodyLeft", parent=BODY, alignment=TA_LEFT)
    BODY_BOLD = ParagraphStyle("BodyBold", parent=BODY, fontName=B.F_DEMI)
    BODY_ITALIC = ParagraphStyle("BodyItalic", parent=BODY, fontName=B.F_ITALIC, alignment=TA_LEFT)
    BULLET = ParagraphStyle("Bullet", parent=BODY, alignment=TA_LEFT,
                            leftIndent=16, bulletIndent=2, spaceAfter=size * 6 / 11.0)
    COL_BODY = ParagraphStyle("ColBody", parent=BODY_LEFT, fontSize=size,
                              leading=size * 13 / 10.0, spaceAfter=size * 8 / 10.0)
    COL_BULLET = ParagraphStyle("ColBullet", parent=COL_BODY, alignment=TA_LEFT,
                                leftIndent=14, bulletIndent=2, spaceAfter=size * 5 / 10.0)
    COL_BODY_BOLD = ParagraphStyle("ColBodyBold", parent=COL_BODY, fontName=B.F_DEMI)


def _set_heading_size(scale):
    """Scale the section-heading styles (H1/H2) up for a policy whose headings
    should read larger than the default (e.g. the Articles of Association, whose
    section titles are only 1 pt above the body at the default size)."""
    global H1, H2
    H1 = ParagraphStyle("H1", fontName=B.F_DEMI, fontSize=14 * scale,
                        leading=16 * scale, textColor=B.BIOMAR_BLUE,
                        spaceBefore=14.5, spaceAfter=15, keepWithNext=1)
    H2 = ParagraphStyle("H2", fontName=B.F_DEMI, fontSize=12 * scale,
                        leading=14 * scale, textColor=B.BIOMAR_BLUE,
                        spaceBefore=5.3, spaceAfter=6.2, keepWithNext=1)


CLAUSE_INDENT = 35.4     # measured from the official Articles of Association (42.6pt margin -> 78.0pt text)
# Lettered sub-items ("a.", "b.", ...) nest one level deeper than the numbered
# clauses: marker at the clause indent (same column as "1.1", "9.6", ...),
# body text at 2x that — per Marianne's reference layout (request 92742ce5):
# her Word doc sets leftIndent=70.8/firstLineIndent=-35.4 on these paragraphs,
# and since that puts the "a." marker's own start already at 35.4, Word's tab
# after it skips the explicit 35.4 tab stop (behind the cursor) and lands on
# the implicit hanging-indent tab at leftIndent=70.8 — so the marker sits at
# the clause indent while the text (first line and wraps alike) sits at 2x it.
# See _set_clause_indent's BULLET_HANG for where this is applied.


def _set_clause_indent(enabled, indent=CLAUSE_INDENT):
    """Hang-indent numbered clauses ("1.1 The Company's...") so wrapped lines
    align under the clause text instead of falling back to the left margin —
    matches the original Articles of Association / Remuneration Policy
    layout. BODY_HANG/_LEFT and BULLET_HANG are separate styles so only
    numbered clauses / lettered items (not every Body/Bullet block) indent.

    The clause number/letter is rendered via ReportLab's Paragraph `bulletText`
    mechanism instead of being embedded in the flowing text: a firstLineIndent
    trick would only push the START of the first line to the margin, but the
    text AFTER the number would still begin wherever that number's own
    (variable) rendered width happens to end — so "3.4" (narrow) and "12.10"
    (wide) would leave their first word at different x positions, out of line
    with the fixed-position wrapped continuation lines below. bulletText draws
    the marker at a fixed `bulletIndent` independent of the paragraph text,
    which then starts at `leftIndent` on EVERY line, first or wrapped alike."""
    global BODY_HANG, BODY_HANG_LEFT, BULLET_HANG, BODY_INDENT, BODY_INDENT_LEFT, H1_HANG, H2_HANG
    if not enabled:
        BODY_HANG, BODY_HANG_LEFT, BULLET_HANG = BODY, BODY_LEFT, BULLET
        BODY_INDENT, BODY_INDENT_LEFT = BODY, BODY_LEFT
        H1_HANG, H2_HANG = H1, H2
        return
    # The clause number is drawn in the same weight as the body text that
    # follows it (Regular, not Demi) — per Marianne's reference layout
    # (request 92742ce5): her doc has no bold/regular contrast between "1.1"
    # and the clause text.
    BODY_HANG = ParagraphStyle("BodyHang", parent=BODY, leftIndent=indent, firstLineIndent=0,
                               bulletIndent=0, bulletFontName=B.F_REGULAR,
                               bulletFontSize=BODY.fontSize, bulletColor=BODY.textColor)
    BODY_HANG_LEFT = ParagraphStyle("BodyHangLeft", parent=BODY_LEFT, leftIndent=indent, firstLineIndent=0,
                                    bulletIndent=0, bulletFontName=B.F_REGULAR,
                                    bulletFontSize=BODY_LEFT.fontSize, bulletColor=BODY_LEFT.textColor)
    BULLET_HANG = ParagraphStyle("BulletHang", parent=BULLET,
                                 leftIndent=indent * 2, firstLineIndent=0,
                                 bulletIndent=indent, bulletFontName=BULLET.fontName,
                                 bulletFontSize=BULLET.fontSize, bulletColor=BULLET.textColor,
                                 spaceAfter=4)
    # Uniform indent (NOT hanging: firstLineIndent=0) for a paragraph that has no
    # clause number of its own but is the content of a numbered sub-heading right
    # above it (e.g. "3.2 Incentive pay" / "The Board of Directors shall not..."):
    # with a hanging indent, a paragraph short enough to never wrap would render
    # its one-and-only line flush at the margin instead of under the clause text.
    BODY_INDENT = ParagraphStyle("BodyIndent", parent=BODY, leftIndent=indent, firstLineIndent=0)
    BODY_INDENT_LEFT = ParagraphStyle("BodyIndentLeft", parent=BODY_LEFT, leftIndent=indent, firstLineIndent=0)
    # A numbered section heading ("1 Name and objects") tab-aligns its title
    # to the same column as the clause text below it — per Marianne's
    # reference layout, where "Name and objects" and "The Company's name..."
    # start at the same x. The number stays Demi (headings are bold either
    # way, unlike clause numbers); bulletFontSize/leading track H1/H2's own
    # (possibly head_scale-d) size, not the fixed defaults.
    H1_HANG = ParagraphStyle("H1Hang", parent=H1, leftIndent=indent, firstLineIndent=0,
                             bulletIndent=0, bulletFontName=B.F_DEMI,
                             bulletFontSize=H1.fontSize, bulletColor=H1.textColor)
    H2_HANG = ParagraphStyle("H2Hang", parent=H2, leftIndent=indent, firstLineIndent=0,
                             bulletIndent=0, bulletFontName=B.F_DEMI,
                             bulletFontSize=H2.fontSize, bulletColor=H2.textColor)


# Minimum visible gap between a clause number/letter and the text that follows
# it. bulletText draws the marker and the body text independently (see
# _set_clause_indent) — nothing stops them from touching or overlapping if the
# marker is wider than the indent, which happens with deeply-nested numbers
# ("4.3.4.1" is ~35.4pt wide at 11pt Demi, the same as CLAUSE_INDENT itself).
MIN_NUMBER_GAP = 4.0


def _required_clause_indent(policy, base=CLAUSE_INDENT):
    """Widen the hang indent for THIS policy if its widest clause number or
    lettered marker would otherwise touch/overlap the text that follows it —
    keeps every clause on the same column (so wrapped lines still line up)
    while guaranteeing a readable gap after the number, even for the deepest
    numbering the document actually uses."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    widest = 0.0
    for b in policy.blocks:
        if isinstance(b, Body) and not getattr(b, "runs", None):
            m = _NUM.match(b.text.strip())
            if m:
                widest = max(widest, stringWidth(m.group(1), B.F_DEMI, BODY.fontSize))
        elif isinstance(b, Bullet):
            lm = _LETTERED_SPLIT.match(b.text.strip())
            if lm:
                widest = max(widest, stringWidth(lm.group(1), BULLET.fontName, BULLET.fontSize))
    return max(base, widest + MIN_NUMBER_GAP)


def build_pdf(policy, out_path):
    _set_body_size(getattr(policy, "body_size", 11) or 11)
    _set_heading_size(getattr(policy, "head_scale", 1.0) or 1.0)
    hanging = getattr(policy, "hanging_indent", False)
    _set_clause_indent(hanging, indent=_required_clause_indent(policy) if hanging else CLAUSE_INDENT)
    doc = BaseDocTemplate(
        out_path, pagesize=(B.PAGE_W, B.PAGE_H),
        leftMargin=B.MARGIN_L, rightMargin=B.MARGIN_R,
        topMargin=B.MARGIN_TOP, bottomMargin=B.MARGIN_BOTTOM,
        title=policy.title, author=B.COMPANY)
    doc._policy = policy

    # The first content page starts high (H1 at the template's 119 pt) only
    # when it begins with a short heading; if it begins with full-width body
    # text, start below the logo so text never runs under it.
    first_top = (B.MARGIN_TOP if (policy.blocks and isinstance(policy.blocks[0], Heading))
                 else B.MARGIN_TOP_CONT)

    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[_frame(B.MARGIN_TOP)], onPage=_draw_cover),
        PageTemplate(id="content_first", frames=[_frame(first_top)],
                     onPage=_draw_content_furniture),
        PageTemplate(id="content", frames=[_frame(B.MARGIN_TOP_CONT)],
                     onPage=_draw_content_furniture),
        PageTemplate(id="signatures", frames=[_frame(B.MARGIN_TOP)],
                     onPage=_draw_signatures),
        PageTemplate(id="back", frames=[_frame(B.MARGIN_TOP)], onPage=_draw_back_cover),
    ])

    # cover | content (first page starts high so the H1 matches the template,
    # later pages start below the logo) | back cover. The board signatures page
    # has been removed from all documents (board composition changed); the
    # "with approval information" variant keeps only the approver/owner/approval
    # card on the back cover, driven by policy.signatures.
    story = ([NextPageTemplate("content_first"), PageBreak(),
              NextPageTemplate("content")] + _story(policy))
    story += [NextPageTemplate("back"), PageBreak(), Spacer(1, 0.1)]
    doc.build(story)
    return out_path
