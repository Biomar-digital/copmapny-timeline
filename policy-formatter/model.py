"""
Parse an incoming Word policy into a simple, render-agnostic content model.

We deliberately keep the model tiny (heading levels, paragraphs, bullets and
tables) because that is everything the BioMar policy template expresses. The
mapping from Word styles to our block types lives here so the generator stays
purely about layout.
"""
from dataclasses import dataclass, field
from typing import List, Optional

import docx
from docx.document import Document as _Doc
from docx.table import Table as _Table
from docx.text.paragraph import Paragraph as _Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P


# ---- block types ----------------------------------------------------------
@dataclass
class Heading:
    level: int          # 1 or 2
    text: str

@dataclass
class Body:
    text: str

@dataclass
class Bullet:
    text: str

@dataclass
class TableBlock:
    rows: List[List[str]]
    header: bool = True

@dataclass
class Policy:
    title: str
    year: str
    blocks: list = field(default_factory=list)


def _iter_block_items(parent):
    """Yield paragraphs and tables in document order."""
    body = parent.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield _Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield _Table(child, parent)


def _clean(text: str) -> str:
    # Word often encodes the clause number + a tab ("3.1\tText"). Collapse the
    # tab to a regular space so it flows as one justified paragraph.
    return text.replace("\t", " ").replace("​", "").strip()


def _heading_level(style_name: str) -> Optional[int]:
    s = (style_name or "").lower()
    if "heading 1" in s or s == "title":
        return 1
    if "heading 2" in s:
        return 2
    return None


def parse_docx(path: str, title: Optional[str] = None,
               year: Optional[str] = None) -> Policy:
    doc = docx.Document(path)
    blocks = []
    lead_lines = []          # text seen before the first real heading
    seen_heading = False

    for item in _iter_block_items(doc):
        if isinstance(item, _Table):
            rows = [[_clean(c.text) for c in row.cells] for row in item.rows]
            rows = [r for r in rows if any(r)]
            if rows:
                blocks.append(TableBlock(rows=rows))
            continue

        text = _clean(item.text)
        style = item.style.name if item.style else "Normal"
        lvl = _heading_level(style)
        is_bullet = "list" in (style or "").lower()

        if lvl:
            seen_heading = True
            if text:
                blocks.append(Heading(level=lvl, text=text))
        elif is_bullet:
            if text:
                blocks.append(Bullet(text=text))
        else:
            if not text:
                continue
            if not seen_heading:
                lead_lines.append(text)   # part of the document title block
            else:
                blocks.append(Body(text=text))

    if title is None:
        title = " ".join(lead_lines).strip() or "Policy"
    if year is None:
        import datetime
        year = str(datetime.date.today().year)

    return Policy(title=title, year=year, blocks=blocks)
