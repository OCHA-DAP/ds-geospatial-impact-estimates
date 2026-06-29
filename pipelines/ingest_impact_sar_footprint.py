"""Manual-delivery loader: IMPACT Sentinel-1 acquisition footprints (VEN).

IMPACT Initiatives shared (by email, 2026-06-29) the true acquisition footprints
behind the Sentinel-1 damage proxy: TWO S1D dual-pol (DV), IW-mode GRD scenes
from 2026-06-25 (acquisition times carried in the `Name` field). This matters
because the damage-proxy raster's bounding rectangle — what we currently use as
the SAR analysed extent (ADR-0008 stopgap) — OVERSTATES coverage: the two swaths
only overlap on ~63% of that rectangle, and IMPACT intentionally masked the
southern/south-eastern single-swath edge ("footprint-aligned inflation", per
their QA). The double-coverage overlap is the honest analysed area.

This lands the provider file to bronze as-received (raw shapefile zip for
provenance) plus a faithful GeoParquet (EPSG:4326, geometry + attributes) for
downstream use. Polygonising the closed outlines and deriving the tightened
analysed_extent (overlap ∩ raster) is a SILVER step, not done here.

The file is a manual delivery, not a re-fetchable source — point GIE_IMPACT_FOOTPRINT_DIR
at the unzipped shapefile directory (defaults to the delivered Downloads path).

Run: GIE_IMPACT_FOOTPRINT_DIR=/path/to/shp_dir \
     uv run --group etl python pipelines/ingest_impact_sar_footprint.py
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import geopandas as gpd
import ocha_stratus as stratus

from gie import ledger
from gie.config import load_settings

SOURCE = "impact_initiatives"
ADM0 = "VE"
STAGE = "dev"
DEFAULT_DIR = (
    "/Users/zackarno/Downloads/IMPACT_VEN_20260625_S1D_postevent_acquisition_footprints"
)
STEM = "Polylines"  # shapefile basename as delivered
ZIP_NAME = "IMPACT_VEN_20260625_S1D_postevent_acquisition_footprints.zip"
PARQUET_NAME = "acquisition_footprints.parquet"


def main() -> None:
    settings = load_settings(STAGE)
    src_dir = Path(os.getenv("GIE_IMPACT_FOOTPRINT_DIR", DEFAULT_DIR))
    parts = sorted(src_dir.glob(f"{STEM}.*"))
    if not parts:
        raise FileNotFoundError(f"No '{STEM}.*' shapefile parts under {src_dir}")

    # 1) raw shapefile as-received -> bronze (zip the sidecar files together)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in parts:
            zf.write(p, p.name)
    raw_blob = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", ZIP_NAME)
    stratus.upload_blob_data(buf.getvalue(), raw_blob, stage=STAGE, container_name=settings.container)

    # 2) faithful GeoParquet (original geometry + attributes, EPSG:4326) -> bronze
    gdf = gpd.read_file(src_dir / f"{STEM}.shp").to_crs(4326)
    pq_blob = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", PARQUET_NAME)
    stratus.upload_parquet_to_blob(
        gdf, pq_blob, stage=STAGE, container_name=settings.container, compression="zstd"
    )

    acq = gdf["Name"].tolist() if "Name" in gdf.columns else []
    print(f"bronze <- {raw_blob}  (raw shapefile, {len(parts)} parts)")
    print(f"bronze <- {pq_blob}  ({len(gdf)} footprints; {gdf.geom_type.iloc[0]}; acq={acq})")

    ledger.record(
        SOURCE,
        "bronze",
        "IMPACT Sentinel-1 acquisition footprints (2 S1D scenes, 2026-06-25) — email delivery",
        settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}"),
        f"{len(gdf)} S1D DV/IW/GRD footprints (acq {acq}); raw shp + GeoParquet; EPSG:4326; "
        "true AOI for tightening the raster-bounds analysed extent (ADR-0008)",
    )


if __name__ == "__main__":
    main()
