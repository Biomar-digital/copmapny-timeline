"""
Rebuild the Guideline cover artwork cleanly:
  1. Recolor the ENTIRE original image (background, decorative pellets, AND
     the soft vignette/shadow behind the badge) to the ocean-blue guideline
     hue via one uniform HLS transform. Doing the whole image in one pass
     (not just the flat background) is the fix — the previous asset only
     recolored the flat background and left the soft vignette behind the
     badge in its original navy tone, which reads as a blurred ghost once
     it's sitting on an ocean-blue page instead of a navy one.
  2. Cut the exact crisp badge (rounded navy card + logo artwork) out of the
     ORIGINAL, untouched image and stamp it back on top of the recolored
     image at the same coordinates — erase, then paste the real logo, per
     spec. A tight rounded-rect alpha mask with only a 2px blur (anti-
     aliasing, not a soft feather) keeps the edge crisp with no seam.
"""
import colorsys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ASSETS = "/home/user/copmapny-timeline/policy-formatter/assets"
TARGET_HEX = "#0471ad"


def hex_to_rgb01(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))


def rgb_to_hls_np(arr):
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    maxc = np.max(arr, axis=-1)
    minc = np.min(arr, axis=-1)
    l = (minc + maxc) / 2.0
    diff = maxc - minc
    s = np.zeros_like(l)
    denom_low = maxc + minc
    denom_high = 2.0 - maxc - minc
    with np.errstate(divide="ignore", invalid="ignore"):
        s_low = np.where(denom_low > 1e-8, diff / np.where(denom_low == 0, 1, denom_low), 0)
        s_high = np.where(denom_high > 1e-8, diff / np.where(denom_high == 0, 1, denom_high), 0)
    s = np.where(l <= 0.5, s_low, s_high)
    s = np.where(diff < 1e-8, 0, s)

    with np.errstate(divide="ignore", invalid="ignore"):
        rc = np.where(diff > 1e-8, (maxc - r) / np.where(diff == 0, 1, diff), 0)
        gc = np.where(diff > 1e-8, (maxc - g) / np.where(diff == 0, 1, diff), 0)
        bc = np.where(diff > 1e-8, (maxc - b) / np.where(diff == 0, 1, diff), 0)
    h = np.where(r == maxc, bc - gc,
        np.where(g == maxc, 2.0 + rc - bc, 4.0 + gc - rc))
    h = np.where(diff < 1e-8, 0, (h / 6.0) % 1.0)
    return h, l, s


def hls_to_rgb_np(h, l, s):
    def _v(m1, m2, hue):
        hue = hue % 1.0
        v = np.where(hue < 1/6, m1 + (m2 - m1) * hue * 6,
            np.where(hue < 0.5, m2,
            np.where(hue < 2/3, m1 + (m2 - m1) * (2/3 - hue) * 6, m1)))
        return v
    m2 = np.where(l <= 0.5, l * (1 + s), l + s - l * s)
    m1 = 2.0 * l - m2
    r = np.where(s == 0, l, _v(m1, m2, h + 1/3))
    g = np.where(s == 0, l, _v(m1, m2, h))
    b = np.where(s == 0, l, _v(m1, m2, h - 1/3))
    return np.stack([r, g, b], axis=-1)


def recolor_image(im, target_hex, sample_xy):
    """Uniform HLS recolor: every pixel keeps its own lightness OFFSET from
    the sampled background lightness, but takes the target hue/saturation —
    background, pellets and the soft vignette all shift consistently."""
    arr = np.asarray(im.convert("RGB")).astype(np.float64) / 255.0
    h, l, s = rgb_to_hls_np(arr)

    bx, by = sample_xy
    bg_r, bg_g, bg_b = arr[by, bx]
    bg_h, bg_l, bg_s = colorsys.rgb_to_hls(bg_r, bg_g, bg_b)
    t_r, t_g, t_b = hex_to_rgb01(target_hex)
    t_h, t_l, t_s = colorsys.rgb_to_hls(t_r, t_g, t_b)

    l_offset = l - bg_l
    new_l = np.clip(t_l + l_offset, 0.0, 1.0)
    new_h = np.full_like(l, t_h)
    new_s = np.full_like(l, t_s)

    out = hls_to_rgb_np(new_h, new_l, new_s)
    out = np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def rounded_mask(size, rect, radius, blur=2):
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle(rect, radius=radius, fill=255)
    if blur:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    return mask


def flatten_vignette(recolored, rect, target_hex, expand=95, blur=55):
    """The original artwork has a soft square vignette/shadow behind the
    badge (barely visible navy-on-navy in the un-recolored covers); the HLS
    pass keeps its lightness dip, so it survives as a visible soft rounded
    shadow once it's sitting on flat ocean blue instead. Erase it: fill a
    generously oversized, heavily-blurred rounded rect at the flat
    background's own recolored tone (== the target hue at full, undipped
    lightness) so the area behind the badge blends seamlessly with the
    rest of the page before the crisp badge gets stamped on top."""
    x0, y0, x1, y1 = rect
    big_rect = (x0 - expand, y0 - expand, x1 + expand, y1 + expand)
    mask = rounded_mask(recolored.size, big_rect, radius=expand, blur=blur)
    flat_rgb = tuple(int(round(c * 255)) for c in hex_to_rgb01(target_hex))
    flat = Image.new("RGB", recolored.size, flat_rgb)
    out = recolored.convert("RGB")
    out.paste(flat, (0, 0), mask)
    return out


def stamp_badge(recolored, original, rect, radius):
    """Cut the crisp badge out of `original` and composite it onto
    `recolored` at `rect`, unmodified — erase + paste, no blending of the
    navy card itself. blur=0.6 is just enough to avoid a jagged/stair-step
    edge on the rounded corners at this resolution — a full 2px (the first
    two rounds used) is wide enough to read as a soft/blurred border once
    the badge is viewed zoomed in, since the badge itself is a small icon
    relative to the page."""
    out = recolored.convert("RGB")
    mask = rounded_mask(out.size, rect, radius, blur=0.6)
    out.paste(original.convert("RGB"), (0, 0), mask)
    return out


def main():
    # Front cover
    front = Image.open(f"{ASSETS}/cover_bg.png")
    front_recolored = recolor_image(front, TARGET_HEX, sample_xy=(50, 50))
    front_flat = flatten_vignette(front_recolored, rect=(1301, 118, 1535, 335), target_hex=TARGET_HEX)
    front_out = stamp_badge(front_flat, front, rect=(1301, 118, 1535, 335), radius=18)
    front_out.save(f"{ASSETS}/cover_bg_guideline.png")
    print("wrote cover_bg_guideline.png", front_out.size)

    # Back cover — unlike the front, measured pixel-by-pixel on all four
    # sides: the flat background sits right up against the badge here with
    # NO vignette dip (front's soft shadow doesn't repeat on this page), so
    # there's nothing to flatten. Skipping it isn't just "less risk" — a big
    # blurred flatten rect here would have bled into real neighbours a
    # generous expand doesn't see coming: a decorative pellet only ~3px
    # above the badge's top edge, and the baked-in "Powered by Partnership /
    # Driven by Innovation" text only ~37px below it (this is what actually
    # broke last round — the flatten rect's own bottom edge landed inside
    # the text's vertical range and partially overwrote it).
    back = Image.open(f"{ASSETS}/cover_bg_back.png")
    back_recolored = recolor_image(back, TARGET_HEX, sample_xy=(50, 50))
    back_out = stamp_badge(back_recolored, back, rect=(680, 1658, 933, 1893), radius=20)
    back_out.save(f"{ASSETS}/cover_bg_back_guideline.png")
    print("wrote cover_bg_back_guideline.png", back_out.size)


if __name__ == "__main__":
    main()
