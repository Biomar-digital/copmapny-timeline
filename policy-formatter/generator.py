"""
Render a Policy content model to a BioMar-branded A4 PDF.

Layout (cover + flowing content pages with running header/footer/logo) is a
faithful reconstruction of the InDesign template. Type scale, colours,
margins and the cover artwork all come from `brand.py` / `assets/`.
"""
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame,
                                Paragraph, Spacer, Table, TableStyle,
                                NextPageTemplate, PageBreak)
from reportlab.platypus.flowables import HRFlowable
from xml.sax.saxutils import escape

import brand as B

B.register_fonts()


# --------------------------------------------------------------------------
# Paragraph stylesheet (mirrors the IDML "Title / Subtitle / Body / Bullets")
# --------------------------------------------------------------------------
# Spacing values mirror the measured template grid (body leading 16, paragraph
# gap 11.4, and the heading spacing reproduced from the IDML Title/Subtitle).
H1 = ParagraphStyle("H1", fontName=B.F_DEMI, fontSize=14, leading=16,
                    textColor=B.BIOMAR_BLUE, spaceBefore=14.5, spaceAfter=15)
H2 = ParagraphStyle("H2", fontName=B.F_DEMI, fontSize=12, leading=14,
                    textColor=B.BIOMAR_BLUE, spaceBefore=5.3, spaceAfter=6.2)
BODY = ParagraphStyle("Body", fontName=B.F_REGULAR, fontSize=11, leading=16,
                      textColor=B.BIOMAR_BLUE, alignment=TA_JUSTIFY, spaceAfter=11.4)
BULLET = ParagraphStyle("Bullet", parent=BODY, alignment=TA_LEFT,
                        leftIndent=16, bulletIndent=2, spaceAfter=6)
CELL = ParagraphStyle("Cell", fontName=B.F_REGULAR, fontSize=8.5, leading=11,
                      textColor=B.BIOMAR_BLUE)
CELL_H = ParagraphStyle("CellH", parent=CELL, fontName=B.F_DEMI,
                        textColor=B.WHITE)
CELL_SEC = ParagraphStyle("CellSec", parent=CELL, fontName=B.F_DEMI)  # section row


def _table(block):
    ncols = max(len(r) for r in block.rows)
    rows = [list(r) + [""] * (ncols - len(r)) for r in block.rows]
    avail = B.PAGE_W - B.MARGIN_L - B.MARGIN_R

    def _is_merged(r):
        f = [c for c in r if c.strip()]
        return len(set(f)) == 1 and len(f) > 1

    # Size columns proportionally to their content length (ignoring merged
    # section rows) with a floor, so text-heavy columns get the width they
    # need and no single row overflows the page.
    body = [r for r in rows if not _is_merged(r)] or rows
    colmax = [max((len(r[c]) for r in body), default=1) for c in range(ncols)]
    colmax = [max(m, 6) for m in colmax]
    tot = sum(colmax)
    colw = [max(avail * m / tot, 34) for m in colmax]
    scale = avail / sum(colw)
    colw = [w * scale for w in colw]

    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, B.LIGHT_RULE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, B.LIGHT_RULE),
    ]
    data = []
    for ri, r in enumerate(rows):
        filled = [c for c in r if c.strip()]
        merged = len(set(filled)) == 1 and len(filled) > 1   # section row
        is_head = block.header and ri == 0
        if merged:
            data.append([Paragraph(escape(filled[0]), CELL_SEC)] + [""] * (ncols - 1))
            style += [("SPAN", (0, ri), (-1, ri)),
                      ("BACKGROUND", (0, ri), (-1, ri), B.LIGHT_RULE)]
        else:
            data.append([Paragraph(escape(c), CELL_H if is_head else CELL) for c in r])
    style.append(("BACKGROUND", (0, 0), (-1, 0), B.BIOMAR_BLUE) if block.header
                  else ("LINEBELOW", (0, 0), (-1, 0), 0.5, B.LIGHT_RULE))
    t = Table(data, colWidths=colw, repeatRows=1 if block.header else 0)
    t.setStyle(TableStyle(style))
    return t


def _story(policy):
    from model import Heading, Body, Bullet, TableBlock
    flow = []
    for b in policy.blocks:
        if isinstance(b, Heading):
            flow.append(Paragraph(escape(b.text), H1 if b.level == 1 else H2))
        elif isinstance(b, Body):
            flow.append(Paragraph(escape(b.text), BODY))
        elif isinstance(b, Bullet):
            flow.append(Paragraph(escape(b.text), BULLET, bulletText="•"))
        elif isinstance(b, TableBlock):
            flow.append(Spacer(1, 4))
            flow.append(_table(b))
            flow.append(Spacer(1, 8))
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
    # White "Version history / Owner and approver" card near the top, drawn on
    # top of the back cover only when approval data is supplied.
    cw, ch = 404.0, 104.0
    cx = (B.PAGE_W - cw) / 2.0
    cy = B.PAGE_H - 150 - ch
    c.setFillColor(B.WHITE)
    c.roundRect(cx, cy, cw, ch, 10, stroke=0, fill=1)

    col2 = cx + cw / 2.0
    head_y = cy + ch - 22
    c.setFillColor(B.BIOMAR_BLUE)
    c.setFont(B.F_DEMI, 10)
    c.drawCentredString(cx + cw / 4.0, head_y, "Version history")
    c.drawCentredString(cx + 3 * cw / 4.0, head_y, "Owner and approver")
    c.setStrokeColor(B.LIGHT_RULE)
    c.setLineWidth(0.5)
    c.line(cx + 12, head_y - 9, cx + cw - 12, head_y - 9)   # under headers
    c.line(col2, cy + 10, col2, head_y - 9)                 # column divider

    rows_l = [(policy.version, policy.approval_date or "—"),
              ("Approval date:", policy.approval_date or "—")]
    rows_r = [("Owner:", policy.owner or "—"),
              ("Approver:", policy.approver or "Executive Committee")]
    c.setFont(B.F_REGULAR, 8)
    ry = head_y - 26
    for (la, va), (lb, vb) in zip(rows_l, rows_r):
        c.setFillColor(B.BIOMAR_BLUE)
        c.drawString(cx + 16, ry, la); c.drawString(cx + 96, ry, va)
        c.drawString(col2 + 16, ry, lb); c.drawString(col2 + 86, ry, vb)
        c.line(cx + 12, ry - 8, cx + cw - 12, ry - 8)
        ry -= 26


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

    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[_frame(B.MARGIN_TOP)], onPage=_draw_cover),
        PageTemplate(id="content_first", frames=[_frame(B.MARGIN_TOP)],
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
