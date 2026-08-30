"""Build the two self-contained HTML reports from the templates in this folder,
embedding the figures from ../figs as data URIs. Output goes to ../data (git-
ignored, like all generated products) — each file is a complete standalone page
that can be opened locally, mailed, or republished as a claude.ai artifact.

Published artifact URLs (private to the account; live copies of these builds):
  technical: https://claude.ai/code/artifact/46583ce9-208b-4d4e-ab86-2f12774352c4
  explainer: https://claude.ai/code/artifact/8370a6df-724a-4a24-85fd-ea7e40065340

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


for tpl, out_name in [
    ("report_template.html", "langtang-sar-precursors.html"),
    ("explainer_template.html", "glacier-explainer.html"),
]:
    with open(os.path.join(HERE, tpl)) as f:
        html = re.sub(r"\{\{FIG:(\w+)\}\}", embed, f.read())
    dst = os.path.join(OUT, out_name)
    with open(dst, "w") as f:
        f.write(html)
    print(f"{len(html) / 1e6:.1f} MB -> {dst}")
