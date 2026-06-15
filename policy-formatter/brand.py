"""
BioMar brand definition for the policy formatter.

All values were reverse-engineered from the official InDesign source
(IDML): the brand colour swatches, the paragraph style sheet (Title /
Subtitle / Body / Bullets), the A4 page geometry and the master-page
margins. Keep this file as the single source of truth for the look.
"""
import os
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
FONT_DIR = os.path.join(ASSETS, "fonts")

LOGO = os.path.join(ASSETS, "logo.png")              # dark square (content pages)
COVER_BG = os.path.join(ASSETS, "cover_bg.png")      # front: logo + rule baked in
COVER_BG_BACK = os.path.join(ASSETS, "cover_bg_back.png")  # back: no logo / rule
COVER_RULE_Y = 252.0                                 # baked rule, pt from bottom

# ---------------------------------------------------------------------------
# Colours  (RGB swatches taken verbatim from the IDML "BioMar" swatch book)
# ---------------------------------------------------------------------------
def _rgb(r, g, b):
    return Color(r / 255.0, g / 255.0, b / 255.0)

# Text/heading colour: the brand swatch is RGB 31/62/119, but the template is
# printed from the CMYK BioMar Blue and renders as #1c4076 - we match the
# template's rendered colour so output is visually identical.
BIOMAR_BLUE   = _rgb(28, 64, 118)    # primary - body text & headings (#1c4076)
# Cover text colours, taken from the template's rendered cover.
COVER_TITLE   = _rgb(186, 229, 244)  # #bae5f4
COVER_YEAR    = _rgb(114, 207, 233)  # #72cfe9
COVER_ADDR    = _rgb(186, 229, 244)  # #bae5f4
CRISP_BLUE    = _rgb(195, 228, 239)
SKY_BLUE      = _rgb(146, 206, 232)
OCEAN_BLUE    = _rgb(4, 113, 173)    # cover blobs / accent boxes
LEAFY_GREEN   = _rgb(151, 209, 48)
SHRIMP_ORANGE = _rgb(221, 105, 40)
WHEAT_YELLOW  = _rgb(234, 179, 24)
WHITE         = _rgb(255, 255, 255)
LIGHT_RULE    = _rgb(195, 228, 239)  # thin separators in tables
TABLE_STRIPE  = _rgb(238, 245, 250)  # zebra striping for table body rows

# ---------------------------------------------------------------------------
# Page geometry (points) - A4, from the IDML master spread
# ---------------------------------------------------------------------------
PAGE_W = 595.276
PAGE_H = 841.890
MARGIN_L = 42.52      # 15 mm
MARGIN_R = 42.52
# First content page starts high (so the H1 lands at the template's 119 pt);
# continuation pages start lower so full-width body text clears the logo,
# matching the template (body resumes ~137 pt from the top there).
MARGIN_TOP = 115.7         # first content page
MARGIN_TOP_CONT = 134.0    # continuation pages (below the logo)
MARGIN_BOTTOM = 56.69

# Logo box (top-right), matches the InDesign placement incl. soft shadow.
LOGO_W = 136.0
LOGO_H = 130.3
LOGO_X = PAGE_W - LOGO_W - 16.6
LOGO_TOP = 16.7       # distance from page top

# Static company details used in the running header / footer / cover.
COMPANY = "BioMar Group"
ADDRESS_LINES = ["BioMar Group", "Kalkværksvej 16, 15.", "8000 Aarhus C", "Denmark"]
WEBSITE = "www.biomar.com"
FOOTER = ("BioMar Group A/S · Kalkværksvej 16, 15. · 8000 Aarhus C · "
          "Denmark · Tel +45 86 20 49 70 · www.biomar.com")
TAGLINE = ["Powered by Partnership", "Driven by Innovation"]

# Board of Directors - signatures page (penultimate). Chair signs centred on
# top, the remaining members in a two-column grid below.
BOARD_CHAIR = "Jens Bjerg Sørensen"
BOARD_MEMBERS = ["Asbjørn Reinkind", "Marianne Kirkegaard",
                 "Jørgen Wisborg", "Anders Wilhjelm"]

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
# Logical weight -> first matching file in assets/fonts is used.
# Drop the licensed "Avenir Next LT Pro" TTFs here to get a pixel-true match;
# otherwise the bundled open fallback (Outfit) is used.
FONT_FALLBACKS = {
    "Light":   ["AvenirNextLTPro-Light.ttf",   "Outfit-Regular.ttf"],
    "Regular": ["AvenirNextLTPro-Regular.ttf", "Outfit-Regular.ttf"],
    "Demi":    ["AvenirNextLTPro-Demi.ttf",    "Outfit-Bold.ttf"],
    "Bold":    ["AvenirNextLTPro-Bold.ttf",    "Outfit-Bold.ttf"],
}

# Public font names used by the stylesheet.
F_LIGHT, F_REGULAR, F_DEMI, F_BOLD = (
    "Brand-Light", "Brand-Regular", "Brand-Demi", "Brand-Bold")
_PSNAMES = {"Light": F_LIGHT, "Regular": F_REGULAR, "Demi": F_DEMI, "Bold": F_BOLD}

_registered = False


def register_fonts():
    """Register the brand font family with ReportLab (idempotent)."""
    global _registered
    if _registered:
        return _using_avenir()
    for weight, candidates in FONT_FALLBACKS.items():
        path = next((os.path.join(FONT_DIR, c) for c in candidates
                     if os.path.exists(os.path.join(FONT_DIR, c))), None)
        if path is None:
            raise FileNotFoundError(f"No font file found for weight '{weight}'")
        pdfmetrics.registerFont(TTFont(_PSNAMES[weight], path))
    _registered = True
    return _using_avenir()


def _using_avenir():
    """True when the real Avenir files are present (affects fidelity note)."""
    return os.path.exists(os.path.join(FONT_DIR, "AvenirNextLTPro-Regular.ttf"))
