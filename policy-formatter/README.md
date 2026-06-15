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
   pages + a back cover, with ReportLab.

| Element        | Spec (from IDML / template)                             |
|----------------|---------------------------------------------------------|
| Page           | A4, margins L/R 15 mm, top 43 mm, bottom 20 mm          |
| Primary colour | BioMar Blue `RGB 31 62 119`                             |
| Cover          | Official empty cover (navy + Ocean-Blue pellet artwork) |
| Title (H1)     | Avenir Next LT Pro Demi 14 pt                           |
| Subtitle (H2)  | Avenir Next LT Pro Demi 12 pt                           |
| Body           | Avenir Next LT Pro Regular 11 pt, justified, 16 pt lead |
| Table header   | Navy background, white Demi text                        |
| Back cover     | Version/owner card + logo + "Powered by Partnership"    |

The back-cover card is filled from the optional `--owner`, `--approver`,
`--approval-date` and `--version` flags.

## Fonts

The template uses the licensed **Avenir Next LT Pro** family. The exact
weights — Light, Regular, **Demi** (headings) and Bold — are converted to
TrueType in `assets/fonts/` and used automatically, so the typography matches
the official template.

* The source fonts are OpenType (`.otf`). ReportLab cannot embed CFF/OpenType
  outlines, so they were converted to `.ttf` with `tools/otf2ttf.py`:

  ```
  python tools/otf2ttf.py AvenirNextLTProDemi.otf assets/fonts/AvenirNextLTPro-Demi.ttf
  ```

  Expected filenames: `AvenirNextLTPro-Light.ttf`, `-Regular.ttf`, `-Demi.ttf`,
  `-Bold.ttf`. If they are ever removed, the code falls back to the bundled
  open **Outfit** font.

## Assets

Regenerate from the source template files with `python tools/build_assets.py`:

* `assets/cover_bg.png` — the official empty cover (navy pellet artwork with the
  logo and decorative rule baked in); the formatter only adds year/title/address.
* `assets/cover_bg_back.png` — same artwork with the logo box and rule removed,
  for the back cover.
* `assets/logo.png` — dark rounded-square logo (white content pages).
* `assets/logo_art.png` — logo art only, transparent (back-cover centre logo).
* `assets/fonts/` — brand fonts (Avenir; Outfit as fallback).

## Turning this into an automatic agent

The CLI is the building block. To make it hands-off, wire `format_policy.py`
to a trigger, e.g.:

* a watched inbox/folder (new `.docx` → run → return `.pdf`), or
* a Claude Code on the web session subscribed to an email/drive source.

Each new policy then comes back already in BioMar format with no manual work.
