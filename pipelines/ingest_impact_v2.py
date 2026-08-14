"""Loader: IMPACT Initiatives Sentinel-1 damage **v2** (vector product) -> bronze.

v2 supersedes the v1 raster damage proxy (ingest_impact_sar.py, which stays for
provenance). Instead of a 10 m z-score raster, IMPACT now deliver the proxy already
intersected with the **common Overture building base**: the buildings whose
footprint is >= 50% covered by the SAR amplitude anomaly — i.e. a per-building
"likely damaged/destroyed" set, directly comparable to the OSU S1 product
(harmonize_osu). Two GeoPackages (EPSG:32619, delivered names kept verbatim):

  * ...Sentinel1_damaged_..._v2.gpkg  — 81,437 damaged Overture footprints.
  * ...analyzed_area_..._v2.gpkg      — the single analysed-area (AOI) polygon.

Method (unchanged from v1, confirmed by the analyst): amplitude/backscatter-
intensity change (NOT coherence — that is OSU), a wide-area screen, not confirmed
damage. See ADR-0008; carry the proxy caveat downstream.

Keying caveat (why harmonization carries geometry rather than a pure id-join like
OSU): `bdg_id` is the unique per-building key (populated for all 81,437). The
Overture GERS `id` is present for the 68,004 Microsoft/Google/OSM-sourced
footprints but **blank for the 13,433 "Venezuela (Bolivarian Republic)"
national-source footprints** — so an id-join would silently drop ~16%. v2 also
spans states our Overture base does not yet cover, so silver uses v2's own geometry.

This lands the two files in bronze as received (raw .gpkg). Harmonization to silver
(building_damage + analysed_extent, superseding the raster-derived impact silver) is
a later step (harmonize_impact_v2.py).

Run: uv run --group etl python pipelines/ingest_impact_v2.py [dir]
     (dir defaults to ~/Documents/global_gis; delivered file names are expected)
"""

from __future__ import annotations

import os
import sys

from gie import blobio, events, ledger
from gie.config import load_settings

SOURCE = "impact_initiatives"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()
DEFAULT_DIR = os.path.expanduser("~/Documents/global_gis")

# (filename, ledger dataset label, ledger detail). Names kept verbatim for
# provenance; 20260625 = post-event acquisition date, v2 = product version.
FILES = [
    (
        "IMPACT_VEN_Earthquake_Sentinel1_damaged_20260625_v2.gpkg",
        "v2 damaged buildings (vector, supersedes raster proxy)",
        "81,437 likely damaged/destroyed Overture footprints (SAR amplitude proxy "
        "covering >=50% of the footprint); fields bdg_id (unique key), id (Overture "
        "GERS; blank for 13,433 national-source footprints), source, bdg_sfc, "
        "b_aff_sf (affected area), adm0-4; EPSG:32619. Supersedes the v1 raster proxy.",
    ),
    (
        "IMPACT_VEN_Earthquake_analyzed_area_20260625_v2.gpkg",
        "v2 analysed-area outline",
        "single AOI polygon (~32,712 km2; fully envelops the v1 analysed extent); the "
        "coverage extent for the common model (analog of CEMS/OSU analysed_extent); "
        "EPSG:32619.",
    ),
]


def main() -> None:
    events.require_event(EVENT)
    src_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    if not os.path.isdir(src_dir):
        raise SystemExit(f"delivery dir not found: {src_dir}")

    settings = load_settings(STAGE)
    fs = blobio.uploader(settings)  # reliable chunked+concurrent upload (36 MB gpkg)

    for name, dataset, detail in FILES:
        src_path = os.path.join(src_dir, name)
        if not os.path.isfile(src_path):
            raise SystemExit(f"missing delivery file: {src_path}")
        blob = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name, event=EVENT)
        with open(src_path, "rb") as f:
            data = f.read()
        print(f"uploading {name} ({len(data) / 1e6:.1f} MB) -> {blob}", flush=True)
        blobio.upload(fs, data, blob)
        # preliminary product — "ingesting" status, matching the other SAR sources.
        ledger.record(SOURCE, "bronze", dataset, blob, detail, status="ingesting")
        print(f"  bronze <- {blob}", flush=True)

    print("done.", flush=True)


if __name__ == "__main__":
    main()
