"""
Render the same parsed Policy model as an editable, BioMar-branded Word (.docx).

This mirrors the PDF (`generator.py`) as closely as Word allows: navy headings
and body, run-in bold labels, bullets, tables, two-column blocks, a title page
and the "Version history / Owner and approver" card, plus the address footer.
It will not be pixel-identical to the PDF (Word lays out columns and fonts
differently), but it is a faithful, editable copy of the same content.
"""
from io import BytesIO

from docx import Document
from docx.shared import Pt, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

import model as M

NAVY = RGBColor(0x1C, 0x40, 0x76)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREY = RGBColor(0x6B, 0x87, 0xA4)
FONT = "Avenir Next LT Pro"          # Word substitutes if the licensed font is absent
FOOTER = ("BioMar Group A/S · Kalkværksvej 16, 15. · 8000 Aarhus C · "
          "Denmark · Tel +45 86 20 49 70 · www.biomar.com")
EMU_PER_PT = 12700


def _set_cell_bg(cell, hex_color):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(shd)


def _no_table_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "none")
        e.set(qn("w:sz"), "0")
        borders.append(e)
    tblPr.append(borders)


def _run(p, text, *, bold=False, size=11, color=NAVY, font=FONT):
    r = p.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    r.font.color.rgb = color
    r.font.name = font
    return r


def _heading(doc, text, level):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(13 if level == 1 else 6)
    p.paragraph_format.space_after = Pt(8 if level == 1 else 4)
    p.paragraph_format.keep_with_next = True
    _run(p, text, bold=True, size=14 if level == 1 else 12)


def _body(doc, blk, size=11):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(10)
    if blk.runs:                              # run-in bold label + plain remainder
        for t, b in blk.runs:
            _run(p, t, bold=b, size=size)
    else:
        _run(p, blk.text, bold=blk.bold, size=size)
    return p


def _bullet(doc, text, size=11):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(4)
    _run(p, text, size=size)


def _table(doc, blk):
    rows = blk.rows
    ncol = max(len(r) for r in rows)
    t = doc.add_table(rows=0, cols=ncol)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    try:
        t.style = "Table Grid"
    except KeyError:
        pass
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for ci in range(ncol):
            txt = row[ci] if ci < len(row) else ""
            cell = cells[ci]
            cell.paragraphs[0].text = ""
            header = blk.header and ri == 0
            if header:
                _set_cell_bg(cell, "1C4076")
            _run(cell.paragraphs[0], txt, bold=header, size=8.5,
                 color=WHITE if header else NAVY)


def _render_blocks(doc, blocks, size=11):
    for blk in blocks:
        if isinstance(blk, M.Heading):
            _heading(doc, blk.text, blk.level)
        elif isinstance(blk, M.Bullet):
            _bullet(doc, blk.text, size)
        elif isinstance(blk, M.TableBlock):
            _table(doc, blk)
        elif isinstance(blk, M.ImageBlock):
            try:
                w = Emu(int(blk.width * EMU_PER_PT)) if blk.width else None
                doc.add_picture(BytesIO(blk.data), width=w)
            except Exception:
                pass
        elif isinstance(blk, M.Columns):
            t = doc.add_table(rows=1, cols=max(len(blk.cols), 1))
            _no_table_borders(t)
            for ci, col in enumerate(blk.cols):
                cell = t.rows[0].cells[ci]
                cell.paragraphs[0].text = ""
                first = True
                for sub in col:
                    # reuse the same renderers, but into the cell
                    _render_into_cell(cell, sub, size, first)
                    first = False
        elif isinstance(blk, M.Body):
            _body(doc, blk, size)


def _render_into_cell(cell, blk, size, first):
    if isinstance(blk, M.Heading):
        p = cell.add_paragraph() if not first else cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0 if first else 8)
        p.paragraph_format.space_after = Pt(4)
        _run(p, blk.text, bold=True, size=12 if blk.level == 1 else 10.5)
    elif isinstance(blk, M.Bullet):
        p = cell.add_paragraph(style="List Bullet")
        _run(p, blk.text, size=size - 1)
    elif isinstance(blk, M.Body):
        p = cell.add_paragraph() if not first else cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if blk.runs:
            for t, b in blk.runs:
                _run(p, t, bold=b, size=size - 1)
        else:
            _run(p, blk.text, bold=blk.bold, size=size - 1)


def _title_page(doc, policy):
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    _run(p, policy.title, bold=True, size=30)
    if policy.cover_year and policy.year:
        p2 = doc.add_paragraph()
        _run(p2, str(policy.year), bold=True, size=20, color=GREY)
    doc.add_page_break()


def _version_card(doc, policy):
    if not any([policy.approval_date, policy.owner, policy.approver]):
        return
    if getattr(policy, "has_signed", False) and not policy.signatures:
        return  # unsigned sibling of a signed doc: no card (matches the PDF)
    doc.add_paragraph()
    t = doc.add_table(rows=1, cols=2)
    try:
        t.style = "Table Grid"
    except KeyError:
        pass
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    left, right = t.rows[0].cells
    _set_cell_bg(left, "1C4076"); _set_cell_bg(right, "1C4076")
    _run(left.paragraphs[0], "Version history", bold=True, size=10, color=WHITE)
    _run(right.paragraphs[0], "Owner and approver", bold=True, size=10, color=WHITE)
    body = t.add_row().cells
    vdate = policy.approval_date or getattr(policy, "version_date", "") or "—"
    lp = body[0].paragraphs[0]
    _run(lp, f"{policy.version} ", bold=True, size=9)
    _run(lp, vdate, size=9)
    if policy.approval_date:
        ap = body[0].add_paragraph()
        _run(ap, "Approval date: ", bold=True, size=9)
        _run(ap, policy.approval_date, size=9)
    op = body[1].paragraphs[0]
    _run(op, "Owner: ", bold=True, size=9)
    _run(op, policy.owner or "—", size=9)
    rp = body[1].add_paragraph()
    _run(rp, "Approver: ", bold=True, size=9)
    _run(rp, policy.approver or "Executive Committee", size=9)


def build_docx(policy, out_path):
    doc = Document()
    # Base style
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(policy.body_size or 11)
    normal.font.color.rgb = NAVY

    section = doc.sections[0]
    # Running header: group + title (small navy)
    h = section.header.paragraphs[0]
    _run(h, f"BioMar Group   ·   {policy.title}", size=8, color=GREY)
    # Footer: address line
    f = section.footer.paragraphs[0]
    f.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(f, FOOTER, size=7.5, color=GREY)

    _title_page(doc, policy)
    if policy.lead_title:
        _heading(doc, policy.title, 1)
    _render_blocks(doc, policy.blocks, size=policy.body_size or 11)
    _version_card(doc, policy)
    doc.save(out_path)
    return out_path
