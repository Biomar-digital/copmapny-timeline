#!/usr/bin/env python3
"""
Adapt an incoming global policy (Word .docx) into a BioMar-branded PDF.

Usage:
    python format_policy.py INPUT.docx [-o OUTPUT.pdf]
                            [--title "Travel Policy"] [--year 2026]

If --title / --year are omitted they are inferred from the document
(title = text before the first heading; year = current year).
"""
import argparse
import os
import sys

from model import parse_docx
from generator import build_pdf
import brand as B


def main(argv=None):
    ap = argparse.ArgumentParser(description="Adapt a Word policy to the BioMar PDF template.")
    ap.add_argument("input", help="Source .docx policy")
    ap.add_argument("-o", "--output", help="Output .pdf (default: alongside input)")
    ap.add_argument("--title", help="Cover / header title (default: inferred)")
    ap.add_argument("--year", help="Cover year (default: current year)")
    # Back-cover "Version history / Owner and approver" card.
    ap.add_argument("--owner", help="Policy owner")
    ap.add_argument("--approver", help="Policy approver")
    ap.add_argument("--approval-date", dest="approval_date", help="Approval date")
    ap.add_argument("--version", help="Version label (e.g. 'Version 1:')")
    # Signatures page (penultimate) adoption statement.
    ap.add_argument("--adopted-on", dest="adopted_on", help="Board adoption date")
    ap.add_argument("--effective-on", dest="effective_on", help="Effective date")
    ap.add_argument("--no-signatures", dest="signatures", action="store_false",
                    help="Omit the board signatures page")
    args = ap.parse_args(argv)

    if not os.path.exists(args.input):
        ap.error(f"input not found: {args.input}")

    out = args.output or os.path.splitext(args.input)[0] + "_BioMar.pdf"
    policy = parse_docx(args.input, title=args.title, year=args.year,
                        owner=args.owner, approver=args.approver,
                        approval_date=args.approval_date, version=args.version,
                        adopted_on=args.adopted_on, effective_on=args.effective_on,
                        signatures=args.signatures)
    build_pdf(policy, out)

    using_avenir = B.register_fonts()
    print(f"✓ {out}")
    print(f"  title='{policy.title}'  year={policy.year}  blocks={len(policy.blocks)}")
    if not using_avenir:
        print("  note: rendered with the open 'Outfit' fallback font. Drop the "
              "licensed Avenir Next LT Pro TTFs into assets/fonts/ for a "
              "pixel-true match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
