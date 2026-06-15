# BioMar Policy Formatter

Turns an incoming **global policy in Word (`.docx`)** into a **BioMar-branded
PDF** that matches the official InDesign template — cover page, running
header/footer, logo, colours, type scale, headings, sub-headings, body,
bullets and tables.

This automates the recurring task of hand-reformatting policies that arrive in
a generic Word layout.

```
python format_policy.py INPUT.docx -o OUTPUT.pdf --title "Travel Policy" --year 2026
```

`--title` and `--year` are optional (title defaults to the text before the
first heading; year defaults to the current year).

## How it works

```
.docx  ──►  model.py      ──►  generator.py   ──►  branded .pdf
            (Word → blocks)     (ReportLab layout)
```

1. **`model.py`** reads the Word file in document order and maps Word styles
   to a small content model: `Heading(1|2)`, `Body`, `Bullet`, `TableBlock`.
2. **`brand.py`** is the single source of truth for the look. Every value
   (colours, A4 geometry, margins, logo placement, fonts, footer text) was
   reverse-engineered from the official **IDML / InDesign source** so the
   output is a faithful reconstruction, not an approximation.
3. **`generator.py`** lays the content into a cover page + flowing content
   pages with ReportLab.

| Element        | Spec (from IDML)                                        |
|----------------|---------------------------------------------------------|
| Page           | A4, margins L/R 15 mm, top 43 mm, bottom 20 mm          |
| Primary colour | BioMar Blue `RGB 31 62 119`                             |
| Cover          | Navy + Ocean-Blue `RGB 4 113 173` pellet artwork        |
| Title (H1)     | Avenir Next LT Pro Demi 14 pt                           |
| Subtitle (H2)  | Avenir Next LT Pro Demi 12 pt                           |
| Body           | Avenir Next LT Pro Regular 11 pt, justified             |
| Table header   | Navy background, white Demi text                        |

## Fonts (important for a pixel-true match)

The template uses the licensed **Avenir Next LT Pro** family. It is not
redistributable, so this repo ships an open geometric fallback (**Outfit**)
and the output is rendered with it by default.

To get an identical match, drop the Avenir TrueType files into
`assets/fonts/` with these names:

```
AvenirNextLTPro-Light.ttf
AvenirNextLTPro-Regular.ttf
AvenirNextLTPro-Demi.ttf
AvenirNextLTPro-Bold.ttf
```

They are picked up automatically (no code change). If you only have the
OpenType (`.otf`) versions, convert them to `.ttf` first (ReportLab cannot
embed CFF/OpenType outlines).

## Assets

* `assets/logo.png` — BioMar icon logo, transparent background.
* `assets/cover_bg.png` — navy cover with the Ocean-Blue pellet artwork,
  derived from the official cover (variable text removed).
* `assets/fonts/` — brand fonts (Avenir if provided, else Outfit fallback).

## Turning this into an automatic agent

The CLI is the building block. To make it hands-off, wire `format_policy.py`
to a trigger, e.g.:

* a watched inbox/folder (new `.docx` → run → return `.pdf`), or
* a Claude Code on the web session subscribed to an email/drive source.

Each new policy then comes back already in BioMar format with no manual work.
