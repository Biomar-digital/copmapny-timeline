#!/usr/bin/env python3
"""
Convert an OpenType (.otf, CFF/PostScript outlines) font to TrueType (.ttf).

ReportLab cannot embed CFF-flavoured OpenType fonts, so the licensed
"Avenir Next LT Pro" OTFs are converted once with this helper. Curves are
approximated as quadratics via cu2qu.

    python tools/otf2ttf.py INPUT.otf OUTPUT.ttf
"""
import sys
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

MAX_ERR = 1.0  # in 1/1000 em


def otf2ttf(src, dst):
    f = TTFont(src)
    order = f.getGlyphOrder()
    glyphs = f.getGlyphSet()
    upm = f["head"].unitsPerEm

    glyf = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = {}
    for name in order:
        pen = TTGlyphPen(glyphs)
        glyphs[name].draw(Cu2QuPen(pen, MAX_ERR * upm / 1000.0))
        glyf[name] = pen.glyph()
    f["glyf"] = glyf

    maxp = newTable("maxp")
    maxp.tableVersion = 0x00010000
    maxp.numGlyphs = len(order)
    for attr in ("maxPoints", "maxContours", "maxCompositePoints",
                 "maxCompositeContours", "maxZones", "maxTwilightPoints",
                 "maxStorage", "maxFunctionDefs", "maxInstructionDefs",
                 "maxStackElements", "maxSizeOfInstructions",
                 "maxComponentElements", "maxComponentDepth"):
        setattr(maxp, attr, 0)
    maxp.maxZones = 1
    f["maxp"] = maxp
    f["loca"] = newTable("loca")
    f["glyf"].compile(f)

    for tag in ("CFF ", "CFF2", "VORG"):
        if tag in f:
            del f[tag]
    if "post" in f:
        f["post"].formatType = 3.0
        f["post"].extraNames = []
        f["post"].mapping = {}
    f.sfntVersion = "\x00\x01\x00\x00"
    f.save(dst)
    print("->", dst)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    otf2ttf(sys.argv[1], sys.argv[2])
