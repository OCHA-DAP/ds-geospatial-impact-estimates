"""Silver: harmonise the IMPACT **v2** vector damage product onto the common model.

Supersedes the raster-derived impact silver (harmonize_impact_sar.py, retained but
unused). v2 is a per-building damaged set on the common Overture base — a building is
kept when the SAR amplitude proxy covers >= 50% of its footprint — a single "likely
damaged/destroyed" class, like OSU (damage_class 2, ADR-0009).

The one departure from OSU: we **carry v2's footprint geometry** rather than id-join
onto our Overture base, because 13,433 national-source buildings have a blank Overture
`id` and the AOI extends beyond the states our base covers — an id-join would drop
~25k of the 81,437 buildings (ADR-0015; exploratory/0002).

Output (source=impact_initiatives, EPSG:4326, replacing the raster silver):
  * building_damage.parquet — one row per damaged building: bdg_id (unique key), id
    (Overture GERS; null where blank), geometry, damage_class(=2), ems_grade,
    affected_fraction (b_aff_sf/bdg_sfc, the confidence signal), source, adm1-3 names.
  * analysed_extent.parquet — the single v2 AOI polygon (the coverage extent).

Run: uv run --group etl python pipelines/harmonize_impact_v2.py
"""

from __future__ import annotations

import io
import os
import tempfile

import geopandas as gpd
import ocha_stratus as stratus

from gie import blobio, ledger
from gie.config import load_settings

SOURCE, ADM0, STAGE = "impact_initiatives", "VE", "dev"
DMG_GPKG = "IMPACT_VEN_Earthquake_Sentinel1_damaged_20260625_v2.gpkg"
AOI_GPKG = "IMPACT_VEN_Earthquake_analyzed_area_20260625_v2.gpkg"


def _read_bronze(settings, name):
    bp = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name)
    raw = stratus.load_blob_data(bp, stage=STAGE, container_name=settings.container)
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tf:
        tf.write(raw)
        tmp = tf.name
    try:
        return gpd.read_file(tmp)
    finally:
        os.unlink(tmp)


def _upload_parquet(fs, frame, blob):
    """Serialise a (Geo)DataFrame to parquet bytes and push via the chunked uploader."""
    buf = io.BytesIO()
    frame.to_parquet(buf, compression="zstd", index=False)
    blobio.upload(fs, buf.getvalue(), blob)


def main() -> None:
    settings = load_settings(STAGE)
    fs = blobio.uploader(settings)

    # damaged buildings -> building_damage.parquet (geometry-carrying) -----------
    dmg = _read_bronze(settings, DMG_GPKG).to_crs(4326)
    ids = dmg["id"].astype(str).str.strip()
    out = gpd.GeoDataFrame(
        {
            "bdg_id": dmg["bdg_id"].astype(str),
            "id": ids.where(ids != "", None),  # national-source blanks -> null
            "damage_class": 2,  # single "likely damaged/destroyed" class (as OSU)
            "ems_grade": "Damaged",
            "affected_fraction": (dmg["b_aff_sf"] / dmg["bdg_sfc"]).clip(upper=1.0),
            "bdg_sfc": dmg["bdg_sfc"],
            "b_aff_sf": dmg["b_aff_sf"],
            "source": dmg["source"].astype(str),
            "adm1_name": dmg["adm1_name"],
            "adm2_name": dmg["adm2_name"],
            "adm3_name": dmg["adm3_name"],
            "geometry": dmg.geometry,
        },
        geometry="geometry",
        crs=4326,
    )
    bd = settings.blob_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "building_damage.parquet")
    _upload_parquet(fs, out, bd)
    print(f"silver <- {bd} ({len(out):,} damaged buildings, geometry-carrying; "
          f"{int(out['id'].notna().sum()):,} with an Overture id)", flush=True)

    # analysed extent -> analysed_extent.parquet (the v2 AOI) --------------------
    aoi = _read_bronze(settings, AOI_GPKG).to_crs(4326)[["geometry"]].copy()
    aoi["source"] = SOURCE
    aoi["superseded"] = False
    ext = settings.blob_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "analysed_extent.parquet")
    _upload_parquet(fs, aoi, ext)
    print(f"silver <- {ext} (v2 AOI polygon)", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "IMPACT v2 vector damage harmonised (geometry-carrying; supersedes raster proxy)",
        bd,
        f"{len(out):,} damaged Overture buildings (damage_class 2 + affected_fraction); "
        "single unioned v2 AOI extent; supersedes the raster-derived impact silver (ADR-0015)",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
