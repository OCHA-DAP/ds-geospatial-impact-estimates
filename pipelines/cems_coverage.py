"""Extract the CEMS analysed extent (coverage mask) -> silver.

CEMS only assesses where it has cloud-free imagery, so its damage counts are a
lower bound biased by coverage. The *analysed* extent per AOI is
imageFootprint - notAnalysed (the imagery actually captured, minus the
cloud/unusable parts; areaOfInterest is only the planned extent and can be
larger). All these shapefiles live in the bronze GRA product zips. Downstream,
the share of an admin unit's buildings inside this extent is its CEMS coverage,
and the observed damage rate can be extrapolated to the rest of the unit
(see harmonize_common).

Run: uv run --group etl python pipelines/cems_coverage.py
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

from gie import ledger
from gie.config import load_settings

ACTIVATION = "EMSR884"
SOURCE = "copernicus_ems"
ADM0 = "VE"
STAGE = "dev"


def _read_layer(zip_bytes: bytes, suffix: str) -> gpd.GeoDataFrame | None:
    with tempfile.TemporaryDirectory() as d:
        zipfile.ZipFile(io.BytesIO(zip_bytes)).extractall(d)
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".shp") and suffix in f:
                    return gpd.read_file(os.path.join(root, f)).to_crs(4326)
    return None


def main() -> None:
    settings = load_settings(STAGE)
    prefix = settings.blob_path("bronze", f"source={SOURCE}", f"code={ACTIVATION}")
    zips = [
        b
        for b in stratus.list_container_blobs(
            name_starts_with=prefix, stage=STAGE, container_name=settings.container
        )
        if b.endswith(".zip") and "GRA" in b
    ]

    parts = []
    for blob in zips:
        data = stratus.load_blob_data(blob, stage=STAGE, container_name=settings.container)
        # imageFootprint = where imagery actually exists (the true coverage);
        # areaOfInterest is only the planned extent and can be larger.
        seen = _read_layer(data, "imageFootprintA")
        if seen is None or len(seen) == 0:
            seen = _read_layer(data, "areaOfInterestA")
        if seen is None or len(seen) == 0:
            continue
        not_analysed = _read_layer(data, "notAnalysedA")
        analysed = seen[["geometry"]]
        if not_analysed is not None and len(not_analysed):
            analysed = gpd.overlay(analysed, not_analysed[["geometry"]], how="difference")
        analysed = analysed.assign(src_zip=blob.split("/")[-1])
        parts.append(analysed)
        print(f"  {blob.split('/')[-1]}: analysed extent ready", flush=True)

    gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
    out = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    stratus.upload_parquet_to_blob(
        gdf, out, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {out} ({len(gdf)} analysed polygons from {len(zips)} GRA products)")
    ledger.record(
        SOURCE,
        "silver",
        "CEMS analysed extent (AOI - not-analysed)",
        out,
        f"{len(gdf)} polygons; coverage mask for detected vs extrapolated",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
