"""Scrape the per-entry tables out of the StEER 2026 Venezuela Earthquake Media Repository PDF.

The PDF is a slide deck. Pages 14-184 alternate between:

  * ENTRY pages — one key/value table per page with four labelled rows
    (Geolocation / Source / Created by / Short Description), followed by annotated photos;
  * SECTION DIVIDER pages — a single large title ("Single-Family Residential",
    "Multi-Family Residential Buildings", "Schools", ...). These are the ONLY place the
    building type is recorded, so the divider title is carried forward as `type` onto every
    entry that follows it.

Two things make naive text extraction wrong, and both are handled here:

  1. The photo callout labels ("detached corner", "infill masonry ejected", ...) sit BELOW the
     table but `page.extract_text()` interleaves them into Short Description. We therefore crop
     to the table's own bounding box and parse only inside it.
  2. "Source: Instagram" is a hyperlink — the actual URL exists only as a PDF annotation, not as
     text. Links are harvested separately and mapped back to the field whose row they overlap.

Output is deliberately RAW: fields are captured as they appear (no coordinate parsing, no
source normalisation) plus `raw_table_text` / `raw_page_text` fallbacks, so that cleaning is a
separate, reviewable step and nothing in the PDF is silently lost.

Run:
  uv run --group etl --with pdfplumber python exploratory/paper/steer/extract_steer_media_repo.py \
      --pdf "/path/to/2026 Venezuela Earthquake Sequence Media Repository.pdf"
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys

import pdfplumber

# The four labelled rows, in the order they appear. Matching is done on a normalised prefix
# because the PDF splits some labels across words and occasionally varies the spacing.
LABELS = [
    ("geolocation", "Geolocation (Address/Coordinates):"),
    ("source", "Source:"),
    ("created_by", "Created by (VAST Member name):"),
    ("short_description", "Short Description:"),
]

FOOTER = "StEER: Building Resilience through Reconnaissance"
PLACEHOLDER = "[Insert image(s) here]"
# Divider slides carry only a title + footer + page number; entry pages run 100+ words.
DIVIDER_MAX_WORDS = 25


def norm(s: str) -> str:
    """Collapse whitespace so label matching survives the PDF's irregular spacing."""
    return re.sub(r"\s+", " ", s).strip()


# Words on one visual line can differ in `top` by a fraction of a point (p130: "Carabobo" at
# 34.07 sits beside "(10.18260," at 33.51). Sorting on the raw coordinate therefore splits a
# line and scrambles reading order, so words are grouped into lines within this tolerance
# first, then ordered left-to-right. Real lines are ~19pt apart, so 4pt cannot merge two.
LINE_TOL = 4.0


def words_to_text(words) -> str:
    """Join words in reading order: group into visual lines, then left-to-right within each."""
    lines: list[dict] = []
    for w in sorted(words, key=lambda w: w["top"]):
        for ln in lines:
            if abs(ln["top"] - w["top"]) <= LINE_TOL:
                ln["ws"].append(w)
                break
        else:
            lines.append({"top": w["top"], "ws": [w]})
    out = []
    for ln in lines:
        ws = sorted(ln["ws"], key=lambda w: w["x0"])
        out.append(" ".join(w["text"] for w in ws))
    return norm(" ".join(out))


def cell_text(page, bbox):
    """Text inside a cell rectangle, using word centres so edge glyphs are not clipped."""
    x0, top, x1, bottom = bbox
    words = [
        w
        for w in page.extract_words()
        if x0 - 2 <= (w["x0"] + w["x1"]) / 2 <= x1 + 2
        and top - 2 <= (w["top"] + w["bottom"]) / 2 <= bottom + 2
    ]
    return words_to_text(words)


def find_entry_table(page):
    """The entry table, identified by how many field labels sit in its left-hand column.

    pdfplumber also reports the slide background and the photo collage as 'tables', and the
    collage is frequently the largest, so size cannot be the selector.
    """
    best = None
    for t in page.find_tables():
        x0, top, x1, bottom = t.bbox
        if (x1 - x0) > 0.95 * page.width and (bottom - top) > 0.95 * page.height:
            continue
        held = 0
        for row in t.rows:
            cells = [c for c in row.cells if c]
            if not cells:
                continue
            text = cell_text(page, cells[0])
            if any(text.startswith(norm(lbl)) for _, lbl in LABELS):
                held += 1
        if held == 0:
            continue
        key = (-held, (x1 - x0) * (bottom - top))  # most labels first, then tightest
        if best is None or key < best[0]:
            best = (key, t)
    return best[1] if best else None


def parse_entry(page):
    """Parse one entry table using its ruled row geometry. Returns (fields, raw_table_text, bbox).

    Row geometry rather than reading order, because the two are not always consistent: on some
    slides a value's text baseline sits a few points ABOVE its own label (p64: the Source value
    is at y=62.4, the "Source:" label at y=68.1). Reading-order parsing attaches such a value to
    the field above it; the ruled rows place it correctly.

    Each label occupies the left column; its value is whatever sits in the right column between
    this label's top and the next label's top (the last runs to the bottom of the table).
    """
    table = find_entry_table(page)
    if table is None:
        return None, "", None
    bbox = table.bbox

    # Locate each label by its left-column cell, keeping that cell's top and right edge.
    found: list[tuple[float, str, float]] = []  # (top, key, left_cell_x1)
    seen: set[str] = set()
    for row in table.rows:
        cells = [c for c in row.cells if c]
        if not cells:
            continue
        left = cells[0]
        text = cell_text(page, left)
        for key, label in LABELS:
            if key not in seen and text.startswith(norm(label)):
                found.append((left[1], key, left[2]))
                seen.add(key)
                break
    if not found:
        return None, cell_text(page, bbox), bbox
    found.sort()

    split = max(f[2] for f in found)  # label/value column boundary
    table_bottom = bbox[3]
    words = page.extract_words()

    fields: dict[str, str] = {}
    bands: dict[str, tuple[float, float]] = {}
    for n, (top, key, _) in enumerate(found):
        bottom = found[n + 1][0] if n + 1 < len(found) else table_bottom
        band = [
            w
            for w in words
            if (w["x0"] + w["x1"]) / 2 >= split - 2
            and top - 1 <= (w["top"] + w["bottom"]) / 2 < bottom + 1
        ]
        text = words_to_text(band).replace(PLACEHOLDER, "").strip()
        fields[key] = norm(text)
        bands[key] = (top, bottom)

    fields["_bands"] = bands  # type: ignore[assignment]
    fields["_split"] = split  # type: ignore[assignment]
    return fields, cell_text(page, bbox), bbox


def divider_title(page):
    """Title text of a section-divider slide, or None if this is not a divider."""
    words = page.extract_words()
    if len(words) > DIVIDER_MAX_WORDS:
        return None
    text = norm(page.extract_text() or "")
    text = text.replace(FOOTER, " ")
    text = re.sub(r"\b\d{1,3}\b", " ", text)  # slide number
    title = norm(text)
    return title or None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--first-page", type=int, default=14, help="1-indexed, inclusive")
    ap.add_argument("--last-page", type=int, default=184, help="1-indexed, inclusive")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "steer_media_repo_raw.csv"))
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        raise SystemExit(f"PDF not found: {args.pdf}")

    rows = []
    dividers = []
    unparsed = []  # pages that are neither a divider nor a parseable entry — reported, never dropped

    with pdfplumber.open(args.pdf) as pdf:
        if args.last_page > len(pdf.pages):
            raise SystemExit(
                f"--last-page {args.last_page} exceeds the document ({len(pdf.pages)} pages)"
            )
        section = None
        # Scan from page 1 so the first emitted entry inherits its section: the
        # "Single-Family Residential" divider sits on p13, i.e. before --first-page.
        for pno in range(1, args.last_page + 1):
            page = pdf.pages[pno - 1]
            raw_page_text = page.extract_text() or ""

            title = divider_title(page)
            if title is not None:
                section = title
                if pno >= args.first_page:
                    dividers.append((pno, title))
                continue

            if pno < args.first_page:
                continue  # front matter: read only for section context

            fields, raw_table_text, bbox = parse_entry(page)
            links = [h.get("uri") for h in page.hyperlinks if h.get("uri")]

            if not fields:
                unparsed.append(pno)
                rows.append(
                    {
                        "pdf_page": pno,
                        "type": section or "",
                        "geolocation": "",
                        "source": "",
                        "created_by": "",
                        "short_description": "",
                        "source_links": "",
                        "all_links": " | ".join(links),
                        "parse_status": "NO_TABLE_FOUND",
                        "raw_table_text": raw_table_text,
                        "raw_page_text": norm(raw_page_text),
                    }
                )
                continue

            bands = fields.pop("_bands")
            fields.pop("_split", None)
            # A link belongs to the Source row if its rectangle overlaps that row vertically.
            src_links = []
            if "source" in bands:
                lo, hi = bands["source"]
                for h in page.hyperlinks:
                    uri = h.get("uri")
                    if not uri:
                        continue
                    htop = h.get("top", h.get("y0", 0))
                    hbot = h.get("bottom", h.get("y1", 0))
                    if hbot >= lo - 2 and htop <= hi + 2:
                        src_links.append(uri)

            missing = [k for k, _ in LABELS if not fields.get(k)]
            rows.append(
                {
                    "pdf_page": pno,
                    "type": section or "",
                    "geolocation": fields.get("geolocation", ""),
                    "source": fields.get("source", ""),
                    "created_by": fields.get("created_by", ""),
                    "short_description": fields.get("short_description", ""),
                    "source_links": " | ".join(dict.fromkeys(src_links)),
                    "all_links": " | ".join(dict.fromkeys(links)),
                    "parse_status": "OK" if not missing else "EMPTY:" + ",".join(missing),
                    "raw_table_text": raw_table_text,
                    "raw_page_text": norm(raw_page_text),
                }
            )

    cols = [
        "pdf_page", "type", "geolocation", "source", "created_by", "short_description",
        "source_links", "all_links", "parse_status", "raw_table_text", "raw_page_text",
    ]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r["parse_status"] == "OK")
    print(f"wrote {args.out}")
    print(f"  entries: {len(rows)}  (fully populated: {ok})")
    print(f"  sections found: {len(dividers)}")
    for pno, t in dividers:
        print(f"    p{pno}: {t}")
    partial = [(r['pdf_page'], r['parse_status']) for r in rows if r["parse_status"].startswith("EMPTY")]
    if partial:
        print(f"  partially populated ({len(partial)}) — check these pages by hand:")
        for pno, st in partial:
            print(f"    p{pno}: {st}")
    if unparsed:
        # Loud on purpose: a page with no table is either a layout we do not handle or a
        # divider we failed to classify. Both need a human look; neither is silently dropped.
        print(f"  NO TABLE FOUND on {len(unparsed)} page(s): {unparsed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
