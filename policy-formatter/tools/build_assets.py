#!/usr/bin/env python3
"""
Regenerate the brand image assets from the official template files.

Produces, in ../assets:
  * cover_bg.png      - the official empty cover (navy + pellet artwork, logo
                        and decorative rule already in place). Used for the
                        front cover; the formatter only adds year/title/address.
  * cover_bg_back.png - same artwork with the top-right logo box and the
                        decorative rule removed, for the back cover.
  * logo.png          - dark rounded-square logo, transparent outside the
                        square (white content pages + back-cover centre logo).

Run once; the results are committed so the formatter has no runtime
dependency on the source files.
"""
import os
import fitz
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.normpath(os.path.join(HERE, "..", "assets"))
SRC = os.environ.get("TEMPLATE_DIR",
                     "/root/.claude/uploads/33deb882-0209-5e9f-8db6-6d3b33cf57ec")
COVER_PDF = os.path.join(SRC, "4b41626f-first_page.pdf")              # empty cover
DARK_LOGO_PDF = os.path.join(SRC, "522c0dfe-2026_Finance_Policy.pdf")  # dark-box logo
LOGO_BOX = (442.7, 16.7, 578.7, 147.0)
NAVY = (31, 62, 119)
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
    img, sc = _render(COVER_PDF, 0, DPI)
    W, H = img.size
    px = img.load()
    # Remove the top-right logo box (plain navy behind it on the back cover).
    ImageDraw.Draw(img).rectangle(
        [int(440 * sc), 0, W, int(160 * sc)], fill=NAVY)
    # Remove the decorative dashed rule (~252 pt from the bottom): replace each
    # light tick with the pixel just below it, preserving navy and blobs.
    rule_y = H - int(252 * sc)
    for y in range(rule_y - 32, rule_y + 32):
        for x in range(W):
            r, g, b = px[x, y]
            if abs(r - 31) + abs(g - 62) + abs(b - 119) > 12:  # tick / anti-alias
                px[x, y] = px[x, min(H - 1, y + 64)]   # copy clean pixel below
    img.save(os.path.join(ASSETS, "cover_bg_back.png"))
    print("cover_bg_back.png", img.size)


def build_art_logo():
    # logo art only (green leaf + cyan swoosh + white wordmark), with the navy
    # rounded square made transparent, for placing directly on the navy back
    # cover (matches the template back page where the logo floats on navy).
    img, sc = _render(DARK_LOGO_PDF, 1, 600)
    box = tuple(int(v * sc) for v in LOGO_BOX)
    crop = img.crop(box).convert("RGBA")
    W, H = crop.size
    # 1) flood the exterior white halo from the corners so it is not mistaken
    #    for the interior white wordmark.
    flooded = crop.convert("RGB")
    MARK = (255, 0, 255)
    for seed in [(0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)]:
        ImageDraw.floodfill(flooded, seed, MARK, thresh=60)
    # 2) keep only the three art colours (white wordmark, cyan swoosh, green
    #    leaf); drop the navy box, its edge ring and the exterior halo.
    px, fp = crop.load(), flooded.load()
    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            white = r > 200 and g > 200 and b > 200
            cyan = r < 140 and g > 140 and b > 150
            green = r < 180 and g > 140 and b < 120
            if fp[x, y] == MARK or not (white or cyan or green):
                px[x, y] = (r, g, b, 0)
    crop.save(os.path.join(ASSETS, "logo_art.png"))
    print("logo_art.png", crop.size)


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
    build_art_logo()
