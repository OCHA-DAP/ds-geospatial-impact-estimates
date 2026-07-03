"""Silver: harmonise DISHA (UN Global Pulse / UNOPS) zero-shot damage -> silver.

DISHA delivered per-building damage predictions (Google Earth AI: Open Buildings +
DA model) over NW Caracas. We take the DAMAGED buildings as damage points (snapped
to the Overture base in harmonize_common, like HOT/CEMS points) plus the AOI as the
analysed extent. Single "damaged" class -> damage_class 2; the model `score` is the
confidence signal.

  !!! LICENCE — staging preview ONLY until UNOPS authorizes !!!
  UNOPS non-commercial; no public display / derivative without prior written UNOPS
  authorization (see ingest_disha.py). This harmonize + the staging preview are for
  the provider's review/approval; do NOT promote to prod until cleared.

Threshold: uses the default `damaged` flag (244 of 38,652 assessed). The delivery
also carries `damaged_high_precision` / `damaged_high_recall` (636 each) — swap
THRESHOLD if a different operating point is wanted (FNR is high, so high_recall may
suit a damage screen better; a product decision).

Output:
  * damage_points.parquet — one row per damaged building (damage_class, score, geom)
  * analysed_extent.parquet — the AOI polygon (coverage extent)

Run: uv run --group etl python pipelines/harmonize_disha.py
"""

from __future__ import annotations

import io
import os
import tempfile

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

from gie import ledger
from gie.config import load_settings

SOURCE, ADM0, STAGE = "disha", "VE", "dev"
DMG_CSV = "NWCaracas_Final_inference_result.csv"
AOI_GEOJSON = "NWCaracas_aoi.geojson"
THRESHOLD = "damaged"  # or damaged_high_precision / damaged_high_recall


def _bronze(settings, name: str) -> bytes:
    bp = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name)
    return stratus.load_blob_data(bp, stage=STAGE, container_name=settings.container)


def main() -> None:
    settings = load_settings(STAGE)

    # damaged buildings -> damage_points (snapped to the base in harmonize_common)
    df = pd.read_csv(io.BytesIO(_bronze(settings, DMG_CSV)))
    dmg = df[df[THRESHOLD] == True]  # noqa: E712 — boolean column
    pts = gpd.GeoDataFrame(
        {
            "building_id": dmg["building_id"].astype(str),
            "score": dmg["score"].astype(float),
            "damage_class": 2,
            "ems_grade": "Damaged",
        },
        geometry=gpd.points_from_xy(dmg["longitude"], dmg["latitude"]),
        crs="EPSG:4326",
    )
    silver = settings.blob_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "damage_points.parquet")
    stratus.upload_parquet_to_blob(
        pts, silver, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {silver} ({len(pts):,} damaged points, threshold={THRESHOLD})", flush=True)

    # AOI -> analysed_extent (the coverage extent)
    with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as tf:
        tf.write(_bronze(settings, AOI_GEOJSON))
        tmp = tf.name
    aoi = gpd.read_file(tmp).to_crs(4326)[["geometry"]].copy()
    os.unlink(tmp)
    aoi["source"] = SOURCE
    aoi["superseded"] = False
    ext = settings.blob_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "analysed_extent.parquet")
    stratus.upload_parquet_to_blob(
        aoi, ext, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {ext} (AOI, {len(aoi)} polygon, ~{aoi.to_crs(32619).area.sum() / 1e6:.0f} km2)", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "DISHA damaged points + AOI extent (LICENCE-gated; staging preview only)",
        silver,
        f"{len(pts):,} damaged buildings (threshold={THRESHOLD}, damage_class 2, score "
        "confidence); AOI ~134 km2; snapped to Overture base in harmonize_common",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
