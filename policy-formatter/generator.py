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
H1 = ParagraphStyle("H1", fontName=B.F_DEMI, fontSize=14, leading=17,
                    textColor=B.BIOMAR_BLUE, spaceBefore=14, spaceAfter=8)
H2 = ParagraphStyle("H2", fontName=B.F_DEMI, fontSize=12, leading=15,
                    textColor=B.BIOMAR_BLUE, spaceBefore=9, spaceAfter=3)
BODY = ParagraphStyle("Body", fontName=B.F_REGULAR, fontSize=11, leading=15.5,
                      textColor=B.BIOMAR_BLUE, alignment=TA_JUSTIFY, spaceAfter=9)
BULLET = ParagraphStyle("Bullet", parent=BODY, alignment=TA_LEFT,
                        leftIndent=16, bulletIndent=2, spaceAfter=6)
CELL = ParagraphStyle("Cell", fontName=B.F_REGULAR, fontSize=8.5, leading=11,
                      textColor=B.BIOMAR_BLUE)
CELL_H = ParagraphStyle("CellH", parent=CELL, fontName=B.F_DEMI,
                        textColor=B.WHITE)


def _table(block):
    data = [[Paragraph(escape(c), CELL_H if (block.header and i == 0) else CELL)
             for c in row] for i, row in enumerate(block.rows)]
    t = Table(data, repeatRows=1 if block.header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, B.LIGHT_RULE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, B.LIGHT_RULE),
    ]
    if block.header:
        style += [("BACKGROUND", (0, 0), (-1, 0), B.BIOMAR_BLUE),
                  ("LINEBELOW", (0, 0), (-1, 0), 0, B.BIOMAR_BLUE)]
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
    c.drawImage(ImageReader(B.COVER_BG), 0, 0, B.PAGE_W, B.PAGE_H,
                preserveAspectRatio=False, mask=None)
    _draw_logo(c)

    # Title - auto-fit width, wrap; anchored so the last line sits just above
    # the decorative rule regardless of how many lines it needs.
    avail = B.PAGE_W - B.MARGIN_L - 30
    size, lines = _fit_title(c, policy.title, avail, 70)
    n = len(lines)
    last_baseline = 318          # baseline of the bottom title line
    c.setFillColor(B.CRISP_BLUE)
    c.setFont(B.F_BOLD, size)
    for i, ln in enumerate(lines):
        c.drawString(B.MARGIN_L, last_baseline + (n - 1 - i) * size * 1.02, ln)
    top_title = last_baseline + (n - 1) * size * 1.02

    # Year sits above the title block.
    c.setFillColor(B.SKY_BLUE)
    c.setFont(B.F_BOLD, 60)
    c.drawString(B.MARGIN_L, top_title + 78, policy.year)

    # Decorative tick rule, just under the title
    rule_y = last_baseline - size * 0.42
    c.setStrokeColor(B.CRISP_BLUE)
    c.setLineWidth(0.6)
    c.setDash(1, 3)
    c.line(B.MARGIN_L, rule_y, B.PAGE_W - B.MARGIN_L, rule_y)
    c.setDash()

    # Address block (bottom-left)
    c.setFillColor(B.CRISP_BLUE)
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


def _draw_logo(c):
    c.drawImage(ImageReader(B.LOGO), B.LOGO_X, B.PAGE_H - B.LOGO_TOP - B.LOGO_H,
                B.LOGO_W, B.LOGO_H, preserveAspectRatio=True, mask="auto")


def _draw_content_furniture(c, doc):
    policy = doc._policy
    # Running header (top-left)
    c.setFillColor(B.BIOMAR_BLUE)
    c.setFont(B.F_REGULAR, 8)
    c.drawString(B.MARGIN_L, B.PAGE_H - 49, B.COMPANY)
    c.drawString(B.MARGIN_L, B.PAGE_H - 49 - 11, policy.title)
    _draw_logo(c)
    # Footer (centred)
    c.setFont(B.F_REGULAR, 8)
    c.drawCentredString(B.PAGE_W / 2.0, 25, B.FOOTER)


def build_pdf(policy, out_path):
    doc = BaseDocTemplate(
        out_path, pagesize=(B.PAGE_W, B.PAGE_H),
        leftMargin=B.MARGIN_L, rightMargin=B.MARGIN_R,
        topMargin=B.MARGIN_TOP, bottomMargin=B.MARGIN_BOTTOM,
        title=policy.title, author=B.COMPANY)
    doc._policy = policy

    frame = Frame(B.MARGIN_L, B.MARGIN_BOTTOM,
                  B.PAGE_W - B.MARGIN_L - B.MARGIN_R,
                  B.PAGE_H - B.MARGIN_TOP - B.MARGIN_BOTTOM,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=_draw_cover),
        PageTemplate(id="content", frames=[frame], onPage=_draw_content_furniture),
    ])

    # Page 1 = cover (drawn by the onPage hook, no flowables); content from p2.
    story = [NextPageTemplate("content"), PageBreak()] + _story(policy)
    doc.build(story)
    return out_path
