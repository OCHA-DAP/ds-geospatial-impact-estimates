"""Idempotent loader: OSU Sentinel-1 'likely damaged areas' delivery -> bronze.

Corey Scher & Jamon Van Den Hoek (Oregon State University) produced a preliminary
Sentinel-1 building-damage assessment for the 24 June 2026 Venezuela earthquake
(USGS us6000t7zp; Copernicus EMS activation EMSR884), distributed via NASA
Disasters (ArcGIS item 200ed651f3b549849c32a2d357662e7d) and a Box package.

Method (Sentinel-1 *coherent change detection* — distinct from the IMPACT
amplitude-z-score proxy):
  * Radar coherence loss between two post-event acquisitions (24 Jun 22:50 UTC,
    near-epicentral; 25 Jun 10:16 UTC, greater Caracas) and a 1-year pre-event
    reference stack, merged into one damage map.
  * A building (Overture footprint) is flagged damaged when >= 50% of its
    footprint area falls on the coherence-loss map. The detection threshold is
    calibrated against the USGS ShakeMap shaking field so the false-alarm rate
    stays <= 1% in lightly-shaken areas (NOT eyeballed).
  * 30 m resolution; ~58,870 buildings flagged; ~75% of dry land within the
    assessed area imaged. Preliminary, unvalidated — an indicator, not a census.

The delivery (all EPSG:4326 GeoPackages) lands here in bronze as received. Each
damaged building carries its `overture_id`, so harmonization to the common model
is an id-join onto our Overture base (99.4% match) plus the analyzed-area polygon
as the coverage extent — no raster sampling (cf. ingest_impact_sar.py). Mapping
to silver/gold is a later step (harmonize_osu.py + harmonize_common.py). See
ADR-0009 for the source-design decisions.

Run: uv run --group etl python pipelines/ingest_osu.py [package-dir]
     (package-dir defaults to ~/Downloads/S1_Damage_Prelim_EMSR884)
"""

from __future__ import annotations

import os
import sys

from azure.storage.blob import ContainerClient

from gie import ledger
from gie.config import load_settings

SOURCE = "osu"
ADM0 = "VE"
STAGE = "dev"
DEFAULT_DIR = os.path.expanduser("~/Downloads/S1_Damage_Prelim_EMSR884")

# (filename, ledger dataset label, ledger detail). Filenames are the delivered
# names (kept verbatim for provenance); the v0 / 20260625 encode the delivery
# version and the most-recent post-event pass.
FILES = [
    (
        "EMSR884_damage_20260625_v0_damaged.gpkg",
        "damaged buildings (quick-look)",
        "58,870 Overture footprints flagged likely damaged/destroyed; fields "
        "overture_id, damage(=1), damage_probability, coverage_fraction(>=0.5), label",
    ),
    (
        "EMSR884_analyzed_area_20260625_v0.gpkg",
        "analyzed-area outline",
        "single polygon of usable S1 coverage (~75% of dry land imaged); the "
        "coverage extent for the common model (analog of CEMS analysed_extent)",
    ),
    (
        "EMSR884_damage_20260625_v0.gpkg",
        "all assessed structures (full)",
        "every Overture footprint in the assessed area (~2.7M) with damage 0/1, "
        "within_coverage, coverage_fraction, damage_probability; archived for "
        "provenance — downstream derives 'analysed' from the analyzed-area polygon",
    ),
    (
        "README.md",
        "delivery README",
        "OSU/NASA delivery notes: method, calibration, coverage, citation, caveats",
    ),
]


def main() -> None:
    pkg_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    if not os.path.isdir(pkg_dir):
        raise SystemExit(f"package dir not found: {pkg_dir}")

    settings = load_settings(STAGE)
    cc = ContainerClient.from_connection_string(
        settings.connection_string(write=True), container_name=settings.container
    )

    for name, dataset, detail in FILES:
        src_path = os.path.join(pkg_dir, name)
        if not os.path.isfile(src_path):
            raise SystemExit(f"missing delivery file: {src_path}")
        blob = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name)
        size = os.path.getsize(src_path)
        print(f"uploading {name} ({size / 1e6:.1f} MB) -> {blob}", flush=True)
        with open(src_path, "rb") as f:
            cc.upload_blob(
                name=blob, data=f, overwrite=True, length=size, max_concurrency=8
            )
        # preliminary v0 delivery — "ingesting" to match the analogous IMPACT
        # SAR source (impact_initiatives), not the stable/final sources.
        ledger.record(SOURCE, "bronze", dataset, blob, detail, status="ingesting")
        print(f"  bronze <- {blob}", flush=True)

    print("done.", flush=True)


if __name__ == "__main__":
    main()
