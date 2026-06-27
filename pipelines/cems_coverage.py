"""Extract the CEMS analysed extent (coverage mask) -> silver.

CEMS only assesses where it has cloud-free imagery, so its damage counts are a
lower bound biased by coverage. The *analysed* extent per AOI is the image
footprint clipped to the area of interest, minus the not-analysed parts:

    (imageFootprintA INTERSECT areaOfInterestA) - notAnalysedA

imageFootprintA alone is the whole satellite scene (far larger than the tasked
area), so it is clipped to areaOfInterestA; notAnalysedA removes cloud / no-data
holes. All these shapefiles live in the bronze GRA product zips. Downstream, the
share of an admin unit's buildings inside this extent is its CEMS coverage, and
the observed damage rate can be extrapolated to the rest of the unit (see
harmonize_common).

Run: uv run --group etl python pipelines/cems_coverage.py
"""

from __future__ import annotations

import io
import os
import re
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


def _zip_meta(src_zip: str, lookup: dict) -> dict:
    """Per-product metadata (AOI, product kind, acquisition) parsed from the
    filename and enriched from the products manifest, for display/hover."""
    aoi_m = re.search(r"AOI(\d+)", src_zip)
    mon_m = re.search(r"MONIT(\d+)", src_zip)
    aoi = int(aoi_m.group(1)) if aoi_m else None
    mon = int(mon_m.group(1)) if mon_m else 0
    name, acq = lookup.get((aoi, mon), (None, None))
    acq_s = acq.strftime("%Y-%m-%d") if acq is not None and pd.notna(acq) else "—"
    return {
        "aoi": aoi,
        "aoi_name": name,
        "product": "Initial product" if mon == 0 else f"Monitoring {mon:02d}",
        "acquired": acq_s,
    }


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

    # acquisition metadata per product, from the latest products manifest
    mans = sorted(
        b
        for b in stratus.list_container_blobs(
            name_starts_with=prefix, stage=STAGE, container_name=settings.container
        )
        if "products_" in b and b.endswith(".parquet")
    )
    meta_lookup: dict = {}
    if mans:
        man = pd.read_parquet(
            io.BytesIO(
                stratus.load_blob_data(mans[-1], stage=STAGE, container_name=settings.container)
            )
        )
        for _, r in man.iterrows():
            if pd.isna(r.get("aoi_number")):
                continue
            mn = r.get("monitoring_number")
            mon = int(mn) if pd.notna(mn) else (1 if r.get("monitoring") else 0)
            meta_lookup[(int(r["aoi_number"]), mon)] = (r.get("aoi_name"), r.get("delivery_time"))

    analysed_parts, detail_parts = [], []
    for blob in zips:
        data = stratus.load_blob_data(blob, stage=STAGE, container_name=settings.container)
        # Valid analysed area = Area of Interest minus the Not-Analysed (cloud /
        # no-imagery) parts within it.
        aoi = _read_layer(data, "areaOfInterestA")
        if aoi is None or len(aoi) == 0:
            continue
        ifp = _read_layer(data, "imageFootprintA")
        not_analysed = _read_layer(data, "notAnalysedA")
        src = blob.split("/")[-1]

        # Image area actually analysed = image footprint clipped to the AOI (the
        # footprint alone is the whole satellite scene, far larger than the
        # tasked area), minus the not-analysed (cloud / no-data) parts within it.
        analysed = aoi[["geometry"]]
        if ifp is not None and len(ifp):
            analysed = gpd.overlay(analysed, ifp[["geometry"]], how="intersection")
        if not_analysed is not None and len(not_analysed):
            analysed = gpd.overlay(analysed, not_analysed[["geometry"]], how="difference")
        meta = _zip_meta(src, meta_lookup)
        analysed_parts.append(analysed.assign(src_zip=src, **meta))

        # the analysed shape + the cloud gaps, with per-product metadata for hover
        detail_parts.append(analysed[["geometry"]].assign(kind="analysed", src_zip=src, **meta))
        if not_analysed is not None and len(not_analysed):
            detail_parts.append(
                not_analysed[["geometry"]].assign(kind="not_analysed", src_zip=src, **meta)
            )
        print(f"  {src}: {meta['aoi_name']} / {meta['product']} ({meta['acquired']})", flush=True)

    analysed_gdf = gpd.GeoDataFrame(pd.concat(analysed_parts, ignore_index=True), crs="EPSG:4326")
    out = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    stratus.upload_parquet_to_blob(
        analysed_gdf, out, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {out} ({len(analysed_gdf)} analysed polygons from {len(zips)} products)")

    detail_gdf = gpd.GeoDataFrame(pd.concat(detail_parts, ignore_index=True), crs="EPSG:4326")
    dout = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "coverage_detail.parquet"
    )
    stratus.upload_parquet_to_blob(
        detail_gdf, dout, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {dout} (analysed + not-analysed shapes for display)")

    ledger.record(
        SOURCE,
        "silver",
        "CEMS analysed extent (AOI - not-analysed) + coverage detail",
        out,
        f"{len(analysed_gdf)} analysed polygons; AOI/not-analysed shapes for display",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
