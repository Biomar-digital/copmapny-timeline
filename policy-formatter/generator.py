"""
Render a Policy content model to a BioMar-branded A4 PDF.

Layout (cover + flowing content pages with running header/footer/logo) is a
faithful reconstruction of the InDesign template. Type scale, colours,
margins and the cover artwork all come from `brand.py` / `assets/`.
"""
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame,
                                Paragraph, Spacer, Table, TableStyle,
                                NextPageTemplate, PageBreak)
from reportlab.platypus.flowables import HRFlowable, BalancedColumns
from xml.sax.saxutils import escape
import re

import brand as B
from model import Heading, Body, Bullet, TableBlock, ImageBlock, Columns
from reportlab.platypus import Image as RLImage
from io import BytesIO

B.register_fonts()


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
BODY = ParagraphStyle("Body", fontName=B.F_REGULAR, fontSize=11, leading=16,
                      textColor=B.BIOMAR_BLUE, alignment=TA_JUSTIFY, spaceAfter=11.4,
                      splitLongWords=0, hyphenationLang="",
                      allowWidows=0, allowOrphans=0)
BODY_LEFT = ParagraphStyle("BodyLeft", parent=BODY, alignment=TA_LEFT)
BULLET = ParagraphStyle("Bullet", parent=BODY, alignment=TA_LEFT,
                        leftIndent=16, bulletIndent=2, spaceAfter=6)
CELL = ParagraphStyle("Cell", fontName=B.F_REGULAR, fontSize=8.5, leading=11,
                      textColor=B.BIOMAR_BLUE, splitLongWords=0, hyphenationLang="")
CELL_H = ParagraphStyle("CellH", parent=CELL, fontName=B.F_DEMI,
                        textColor=B.WHITE, alignment=TA_CENTER)        # column header
CELL_SEC = ParagraphStyle("CellSec", parent=CELL, fontName=B.F_DEMI,
                          textColor=B.WHITE)                            # section band row
CELL_C = ParagraphStyle("CellC", parent=CELL, alignment=TA_CENTER)     # short marks (√, —)


_NUM = re.compile(r"^(\d+(?:\.\d+)*\.?)(\s+)(.*)$", re.S)


def _fmt(text, number=True, widow=True):
    """Format clause text: (1) keep the last two words together so a paragraph
    never ends with a single orphaned word; (2) render a leading clause number
    (e.g. '2.3.2') in Demi. Headings are already fully Demi, so this is used
    for body/bullets/cells only."""
    t = text.strip()
    if widow:
        parts = t.rsplit(" ", 1)
        if len(parts) == 2:
            t = parts[0] + " " + parts[1]   # glue last two words (no widow)
    m = _NUM.match(t) if number else None
    if m:
        return (f'<font name="{B.F_DEMI}">{escape(m.group(1))}</font>'
                f'{m.group(2)}{escape(m.group(3))}')
    return escape(t)


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


def _body_cells(r, ncols):
    """Return (cells, is_band) for one body row."""
    if _band(r):
        txt = [c for c in r if c.strip()][0]
        return [Paragraph(escape(txt), CELL_SEC)] + [""] * (ncols - 1), True
    return [Paragraph(escape(c) if len(c.strip()) <= 2 else _fmt(c, widow=False),
                      CELL_C if len(c.strip()) <= 2 else CELL)
            for c in r], False


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
            out.append(Paragraph(_fmt(sb.text), BULLET, bulletText="•"))
        else:
            out.append(Paragraph(_fmt(sb.text), BODY_LEFT))
    return out


def _columns_flowables(b):
    """Render two text columns as a borderless table whose rows pair the items
    of each column. Reading a column top-to-bottom gives that column's items in
    order; the table splits between rows so it paginates across pages."""
    cols = [c for c in b.cols if c]
    if not cols:
        return []
    if len(cols) == 1:
        return _col_flowables(cols[0])
    left = _col_flowables(cols[0])
    right = _col_flowables(cols[1])
    n = max(len(left), len(right))
    left += [""] * (n - len(left))
    right += [""] * (n - len(right))
    half = (_CONTENT_W - 16) / 2
    t = Table([[left[i], right[i]] for i in range(n)], colWidths=[half, half])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 16),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [Spacer(1, 4), t, Spacer(1, 6)]


def _story(policy):
    flow = []
    for b in policy.blocks:
        if isinstance(b, Heading):
            flow.append(Paragraph(escape(b.text), H1 if b.level == 1 else H2))
        elif isinstance(b, Body):
            # Justify normal running text; left-align short lines and anything
            # with a URL/long token so justification doesn't stretch the spaces.
            justify = len(b.text) >= 90 and "://" not in b.text
            flow.append(Paragraph(_fmt(b.text), BODY if justify else BODY_LEFT))
        elif isinstance(b, Bullet):
            flow.append(Paragraph(_fmt(b.text), BULLET, bulletText="•"))
        elif isinstance(b, TableBlock):
            flow.append(Spacer(1, 4))
            flow.extend(_table_flowables(b))
            flow.append(Spacer(1, 8))
        elif isinstance(b, ImageBlock):
            flow.extend(_image_flowables(b))
        elif isinstance(b, Columns):
            flow.extend(_columns_flowables(b))
    return flow


# --------------------------------------------------------------------------
# Page furniture
# --------------------------------------------------------------------------
def _draw_cover(c, doc):
    policy = doc._policy
    # The official empty cover already has the navy pellet artwork, the logo
    # and the decorative rule baked in; we only add the year, title and address.
    c.drawImage(ImageReader(B.COVER_BG), 0, 0, B.PAGE_W, B.PAGE_H,
                preserveAspectRatio=False, mask=None)

    # Title - auto-fit width, wrap; anchored so the bottom line sits just above
    # the baked rule, with the year stacked above it.
    avail = B.PAGE_W - B.MARGIN_L - 30
    size, lines = _fit_title(c, policy.title, avail, 70)
    n = len(lines)
    last_baseline = B.COVER_RULE_Y + 65.6    # bottom title line, matches template
    c.setFillColor(B.COVER_TITLE)
    c.setFont(B.F_BOLD, size)
    for i, ln in enumerate(lines):
        c.drawString(B.MARGIN_L, last_baseline + (n - 1 - i) * size * 1.02, ln)
    top_title = last_baseline + (n - 1) * size * 1.02

    # Year sits above the title block.
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
    # Footer (centred)
    c.setFont(B.F_REGULAR, 8)
    c.drawCentredString(B.PAGE_W / 2.0, 25, B.FOOTER)


def _draw_back_cover(c, doc):
    policy = doc._policy
    # The official empty back cover already has the pellet artwork, the logo,
    # the tagline and the URL baked in; we only overlay the optional card.
    c.drawImage(ImageReader(B.COVER_BG_BACK), 0, 0, B.PAGE_W, B.PAGE_H,
                preserveAspectRatio=False, mask=None)
    if any([policy.approval_date, policy.owner, policy.approver]):
        _draw_version_card(c, policy)


def _draw_version_card(c, policy):
    # White "Version history / Owner and approver" card, drawn on the back
    # cover only when approval data is supplied. Layout (column x-positions,
    # Light 8 pt labels/values, Demi 10 pt headers) matches the template card.
    cw, ch = 380.0, 100.0
    cx = (B.PAGE_W - cw) / 2.0          # page-centred, like the template
    cy = B.PAGE_H - 150 - ch
    right = cx + cw
    c.setFillColor(B.WHITE)
    c.roundRect(cx, cy, cw, ch, 10, stroke=0, fill=1)

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

    rows_l = [(policy.version, policy.approval_date or "—"),
              ("Approval date:", policy.approval_date or "—")]
    rows_r = [("Owner:", policy.owner or "—"),
              ("Approver:", policy.approver or "Executive Committee")]
    ry = head_y - 27
    for (la, va), (lb, vb) in zip(rows_l, rows_r):
        c.setFillColor(B.BIOMAR_BLUE)
        c.setFont(B.F_LIGHT, 8)
        c.drawRightString(L_LABEL_R, ry, la)
        c.drawString(L_VALUE, ry, va)
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


def build_pdf(policy, out_path):
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
    # later pages start below the logo) | [signatures] | back cover.
    story = ([NextPageTemplate("content_first"), PageBreak(),
              NextPageTemplate("content")] + _story(policy))
    if policy.signatures:
        story += [NextPageTemplate("signatures"), PageBreak(), Spacer(1, 0.1)]
    story += [NextPageTemplate("back"), PageBreak(), Spacer(1, 0.1)]
    doc.build(story)
    return out_path
