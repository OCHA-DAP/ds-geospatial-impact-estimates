"""Build the combined HTML report (plain-language spine + expandable technical
panels) from combined_template.html, embedding the figures from ../figs as data
URIs. The page is fully self-contained and is written to two places:

  ../data/langtang-sar-precursors.html     local copy (data/ is git-ignored)
  ../../../pages/langtang-sar-precursors/index.html
                                           the pages-site copy (committed —
                                           pages/ deploys as-is on push to v1)

A live copy is also published as a claude.ai artifact (account-private):
https://claude.ai/code/artifact/8370a6df-724a-4a24-85fd-ea7e40065340
(An earlier separate technical artifact, 46583ce9…, is superseded by this
combined page.)

Run figures first (analysis.py, falsealarms_analysis.py, offset_tracking.py), then:
  uv run python exploratory/0005-nepal-glof-sar-precursor/reports/build_reports.py
"""
from __future__ import annotations

import base64
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "..", "figs")
OUT = os.path.join(HERE, "..", "data")
PAGES = os.path.join(HERE, "..", "..", "..", "pages", "langtang-sar-precursors")
os.makedirs(OUT, exist_ok=True)

ALTS = {
    "scar_map": "Post-event SAR change map showing the detachment scar and runout",
    "raw_vv_doy": "Raw VV backscatter by day of year, 2026 vs 2020-2025, three orbits",
    "climatology_z": "Climatological z-scores for source and control boxes, three orbits",
    "divergence_z": "Source-minus-controls divergence z by orbit and local time",
    "preevent_fraction": "Anomalous pixel share inside vs outside the future scar",
    "falsealarm_runstat": "Detector replay over 45 faces and 5 seasons: one dot per "
                          "face-season, alarm threshold marked, collapse face highlighted",
    "offset_tracking": "Speckle offset tracking displacement maps, final pre-event "
                       "pairs vs reference pairs, no motion patch in the source box",
}


def embed(match: re.Match) -> str:
    name = match.group(1)
    path = os.path.join(FIGS, f"{name}.png")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} missing — run the analysis scripts to regenerate figures first"
        )
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f'<img src="data:image/png;base64,{b64}" alt="{ALTS[name]}">'


with open(os.path.join(HERE, "combined_template.html")) as f:
    html = re.sub(r"\{\{FIG:(\w+)\}\}", embed, f.read())

# The pages site serves this standalone, so it needs a full document skeleton;
# the artifact publisher adds its own, so the data/ copy stays as a fragment.
dst = os.path.join(OUT, "langtang-sar-precursors.html")
with open(dst, "w") as f:
    f.write(html)
print(f"{len(html) / 1e6:.1f} MB -> {dst}")

os.makedirs(PAGES, exist_ok=True)
# a <title> inside <body> is ignored by browsers, so lift it into the head
title = re.search(r"<title>.*?</title>", html).group(0)
# per the team pages convention (KB: methods/static-data-apps.md, "Nested pages
# link back home"): a self-contained back-to-home link as the first element in
# <body>, relative href, labelled with what it links back to. Pages copy only —
# the claude.ai artifact has no landing page above it.
home_link = (
    "<style>.home-link{display:inline-block;margin:10px 12px;padding:6px 12px;"
    "font:500 13px/1 'IBM Plex Mono',monospace;color:#2a78d6;background:#eaf2fb;"
    "border:1px solid #c9ddf3;border-radius:4px;text-decoration:none}"
    ".home-link:hover{background:#dcebf9}</style>\n"
    '<a class="home-link" href="../">← All analysis &amp; tools</a>\n'
)
page = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{title}\n</head>\n<body>\n{home_link}"
        + html.replace(title, "", 1) + "\n</body>\n</html>\n")
with open(os.path.join(PAGES, "index.html"), "w") as f:
    f.write(page)
print(f"{len(page) / 1e6:.1f} MB -> {os.path.join(PAGES, 'index.html')}")
