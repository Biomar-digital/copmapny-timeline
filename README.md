# BioMar Policy System

A self-contained system for producing and publishing BioMar-branded policy
documents. **Everything lives in this repository** — the tool, the source
documents, the generated PDFs and the metadata — and there is **no backend and
no API**.

* **View** the catalogue on the static web page (`docs/`).
* **Create / edit** policies by connecting **Claude Code** to this repository
  (the way the library is administered — no admin server needed).

```
repo/
├── policy-formatter/        the converter (.docx → BioMar PDF) + tools
│   ├── format_policy.py     CLI: one .docx → one branded PDF
│   ├── brand.py             colours, geometry, fonts (single source of truth)
│   ├── generator.py         layout engine (cover, content, signatures, back)
│   ├── model.py             .docx → content model (robust to messy styling)
│   ├── assets/              logo, cover artwork, Avenir fonts
│   └── tools/
│       ├── build_assets.py  regenerate brand images from the templates
│       ├── otf2ttf.py       convert Avenir .otf → .ttf
│       └── publish.py       generate all PDFs + refresh docs/library.json
├── policies/
│   ├── sources/             the incoming Word documents (.docx)
│   └── registry.json        source of truth: title, owner, approver, dates …
└── docs/                    the static web library (GitHub Pages root)
    ├── index.html app.js styles.css
    ├── library.json         generated index the page reads
    └── files/               generated PDFs (approval / non-approval)
```

## The web library (`docs/`)

A static page that reads `docs/library.json` and lists every policy with its
language, owner, approver, version, dates and edition history, plus download
links to both PDF variants. No build step, no server code.

**Publish online with GitHub Pages:** repo *Settings → Pages → Source: deploy
from branch → folder `/docs`*. To preview locally:

```
cd docs && python -m http.server   # then open http://localhost:8000
```

## Administering via Claude Code

Connect Claude Code to this repo and ask in plain language, e.g.:

* *"Add a new policy from this .docx (owner X, approver Y) and publish it."*
* *"Change the owner of the Tax Policy to Group Tax and regenerate."*
* *"Regenerate the Diversity Policy without the approval pages."*

Under the hood that means: drop the `.docx` in `policies/sources/`, edit
`policies/registry.json`, run `python policy-formatter/tools/publish.py`, and
commit. The web page updates automatically from the repo.

### Each policy produces two PDFs

* **approval** — board signatures page (penultimate) + version/owner card (back).
* **non-approval** — neither.

File names: `<Title>_<YYYY-MM>_<approval|non-approval>.pdf`.

## The PDF format

Faithful reconstruction of the official InDesign template: A4, Avenir Next LT
Pro (Demi headings / Regular body), BioMar Blue `#1c4076`, official cover and
back-cover artwork, branded tables (navy header, Ocean-Blue section bands,
zebra rows, full grid), and typographic safeguards (no text under the logo, no
orphaned headings or section bands, repeated table headers across pages). See
`policy-formatter/README.md` for details.

## Setup

```
pip install -r policy-formatter/requirements.txt
python policy-formatter/tools/publish.py      # (re)build the whole library
```
