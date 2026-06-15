#!/usr/bin/env python3
"""
Regenerate the brand image assets from the official template files.

Produces, in ../assets:
  * cover_bg.png      - the official empty front cover (navy + pellet artwork,
                        logo and decorative rule baked in). The formatter only
                        adds year/title/address.
  * cover_bg_back.png - the official empty back cover (pellet artwork, logo,
                        tagline and URL baked in). The formatter only overlays
                        the optional version/owner card.
  * logo.png          - dark rounded-square logo, transparent outside the
                        square, for the white content pages.

Run once; the results are committed so the formatter has no runtime
dependency on the source files.
"""
import os
import fitz
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.normpath(os.path.join(HERE, "..", "assets"))
SRC = os.environ.get("TEMPLATE_DIR",
                     "/root/.claude/uploads/33deb882-0209-5e9f-8db6-6d3b33cf57ec")
COVER_PDF = os.path.join(SRC, "4b41626f-first_page.pdf")               # empty front
BACK_PDF = os.path.join(SRC, "66261cf9-last_page.pdf")                # empty back
DARK_LOGO_PDF = os.path.join(SRC, "522c0dfe-2026_Finance_Policy.pdf")  # dark-box logo
LOGO_BOX = (442.7, 16.7, 578.7, 147.0)
DPI = 200


def _render(pdf, page, dpi):
    doc = fitz.open(pdf)
    sc = dpi / 72.0
    pix = doc[page].get_pixmap(matrix=fitz.Matrix(sc, sc))
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("RGB")
    doc.close()
    return img, sc


def build_cover_bg():
    img, _ = _render(COVER_PDF, 0, DPI)
    img.save(os.path.join(ASSETS, "cover_bg.png"))
    print("cover_bg.png", img.size)


def build_back_bg():
    img, _ = _render(BACK_PDF, 0, DPI)
    img.save(os.path.join(ASSETS, "cover_bg_back.png"))
    print("cover_bg_back.png", img.size)


def build_dark_logo():
    img, sc = _render(DARK_LOGO_PDF, 1, 600)
    box = tuple(int(v * sc) for v in LOGO_BOX)
    crop = img.crop(box).convert("RGBA")
    px = crop.load()
    W, H = crop.size
    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            m = min(r, g, b)
            if m > 185:                                # white halo -> transparent
                px[x, y] = (r, g, b, 0)
            elif m > 150:                              # soft edge -> feather
                px[x, y] = (r, g, b, int((255 - m) / (255 - 150) * 255))
    crop.save(os.path.join(ASSETS, "logo.png"))
    print("logo.png", crop.size)


if __name__ == "__main__":
    build_cover_bg()
    build_back_bg()
    build_dark_logo()
