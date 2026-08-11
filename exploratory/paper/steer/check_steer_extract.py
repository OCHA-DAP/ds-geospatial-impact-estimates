"""Self-check the StEER extraction: does every word inside each table land in a field?

Two failure modes matter and neither shows up as an empty cell:

  * DROPPED text — a value that exists in the PDF but reached no column (e.g. a wrapped line
    that fell outside every band). Detected by differencing the words inside the table's
    bounding box against the words captured across the four fields + the labels themselves.
  * CONTAMINATION — photo callout text from BELOW the table leaking into Short Description.
    Detected by differencing the other way: captured words that do not exist inside the table.

Both are reported per page; a clean run prints zero of each.

Run:
  uv run --group etl --with pdfplumber python exploratory/paper/steer/check_steer_extract.py \
      --pdf "/path/to/....pdf"
"""
from __future__ import annotations

import argparse
import collections
import csv
import os
import re

import pdfplumber
from pdfplumber.utils import cluster_objects

from extract_steer_media_repo import (
    LABELS,
    PLACEHOLDER,
    find_entry_table,
    norm,
    parse_entry,
)


def tokens(s: str):
    """Word bag, punctuation-insensitive, for set-differencing two renderings of the same text."""
    return collections.Counter(t for t in re.findall(r"[0-9A-Za-zÀ-ÿ@._/:+-]+", (s or "").lower()) if t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "steer_media_repo_raw.csv"))
    args = ap.parse_args()

    rows = {int(r["pdf_page"]): r for r in csv.DictReader(open(args.csv, encoding="utf-8"))}
    label_tokens = collections.Counter()
    for _, lbl in LABELS:
        label_tokens.update(tokens(lbl))
    label_tokens.update(tokens(PLACEHOLDER))

    dropped_pages, contaminated_pages, order_pages = [], [], []
    with pdfplumber.open(args.pdf) as pdf:
        for pno, row in sorted(rows.items()):
            page = pdf.pages[pno - 1]
            table = find_entry_table(page)
            if table is None:
                print(f"  p{pno}: NO TABLE (unexpected)")
                continue
            x0, top, x1, bottom = table.bbox
            in_table = collections.Counter()
            for w in page.extract_words():
                cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
                if x0 - 2 <= cx <= x1 + 2 and top - 2 <= cy <= bottom + 2:
                    in_table.update(tokens(w["text"]))

            captured = collections.Counter()
            for k in ("geolocation", "source", "created_by", "short_description"):
                captured.update(tokens(row[k]))

            dropped = in_table - captured - label_tokens
            extra = captured - in_table
            if dropped:
                dropped_pages.append((pno, dict(dropped)))
            if extra:
                contaminated_pages.append((pno, dict(extra)))

            # Reading order, checked independently of band assignment: re-group the SAME words
            # we assigned to each field using pdfplumber's own cluster_objects, then order each
            # cluster left-to-right. Agreement means our line-grouping tolerance is not
            # inventing an order. (A bag-of-words check cannot see this: p130 once emitted the
            # coordinates before "Carabobo - National Monument" because two words on one line
            # differed in `top` by 0.56pt.)
            fields, _, _ = parse_entry(page)
            if not fields:
                continue
            bands, split = fields.pop("_bands"), fields.pop("_split")
            for key, (btop, bbot) in bands.items():
                band = [
                    w
                    for w in page.extract_words()
                    if (w["x0"] + w["x1"]) / 2 >= split - 2
                    and btop - 1 <= (w["top"] + w["bottom"]) / 2 < bbot + 1
                ]
                if not band:
                    continue
                clusters = cluster_objects(band, lambda w: w["top"], 3)
                ref = norm(
                    " ".join(
                        " ".join(w["text"] for w in sorted(c, key=lambda w: w["x0"]))
                        for c in clusters
                    )
                ).replace(PLACEHOLDER, "")
                got = norm(row[key])
                if norm(ref).replace(" ", "") != got.replace(" ", ""):
                    order_pages.append((pno, key, norm(ref)[:90], got[:90]))

    print(f"checked {len(rows)} entry pages")
    print(f"  pages with DROPPED table text: {len(dropped_pages)}")
    for pno, d in dropped_pages[:15]:
        print(f"    p{pno}: {list(d)[:12]}")
    print(f"  pages with text captured that is NOT in the table: {len(contaminated_pages)}")
    for pno, d in contaminated_pages[:15]:
        print(f"    p{pno}: {list(d)[:12]}")
    print(f"  field values disagreeing with pdfplumber's own layout: {len(order_pages)}")
    for pno, key, ref, got in order_pages[:15]:
        print(f"    p{pno} {key}\n        pdfplumber: {ref}\n        ours      : {got}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
