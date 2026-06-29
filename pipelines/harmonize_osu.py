"""Project the OSU Sentinel-1 coherence damage assessment onto the Overture base -> silver.

See ADR-0009 for the design decisions (id-join over geometry, damage_class
mapping, analyzed-area polygon as extent, damaged-only per-building stopgap).

OSU (Corey Scher & Jamon Van Den Hoek, Oregon State University) delivered
building-level damage already keyed to Overture footprints (`overture_id`), so —
unlike the IMPACT raster proxy (ingest/harmonize_impact_sar) — there is no raster
sampling: the damaged set is a straight id-join onto our Overture base (99.4%
match), and the analyzed-area polygon is the coverage extent.

Method recap (from the delivery README, in bronze): Sentinel-1 *coherent change
detection* — coherence loss between two post-event passes and a 1-year pre-event
stack. A building is flagged when >= 50% of its footprint falls on the
coherence-loss map; the threshold is calibrated against the USGS ShakeMap field
so the false-alarm rate stays <= 1% in lightly-shaken areas. It is a single
"likely damaged/destroyed" class -> damage_class 2 (Damaged) on the xBD/CEMS
scale; `damage_probability` is the model score, carried as the confidence signal.
Preliminary, unvalidated — an indicator, not a building-by-building census.

Output (mirrors source=impact_initiatives):
  * building_damage.parquet — one row per OSU-damaged building (id, damage_class,
    damage_probability, ems_grade). No geometry: `id` joins onto the Overture base.
  * analysed_extent.parquet — the analyzed-area polygon (the coverage extent).

Run: uv run --group etl python pipelines/harmonize_osu.py
"""

from __future__ import annotations

import os
import tempfile

import geopandas as gpd
import ocha_stratus as stratus

from gie import ledger
from gie.config import load_settings

SOURCE = "osu"
ADM0 = "VE"
STAGE = "dev"
DAMAGED_GPKG = "EMSR884_damage_20260625_v0_damaged.gpkg"
AOI_GPKG = "EMSR884_analyzed_area_20260625_v0.gpkg"


def _read_gpkg(settings, name, columns=None):
    """Pull a bronze GeoPackage to a temp file and read it (the azure driver does
    not read .gpkg straight from blob)."""
    bpath = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name)
    raw = stratus.load_blob_data(bpath, stage=STAGE, container_name=settings.container)
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tf:
        tf.write(raw)
        tmp = tf.name
    try:
        return gpd.read_file(tmp, columns=columns)
    finally:
        os.unlink(tmp)


def main() -> None:
    settings = load_settings(STAGE)

    # damaged buildings -> building_damage.parquet (id-keyed, no geometry).
    dmg = _read_gpkg(settings, DAMAGED_GPKG, columns=["overture_id", "damage_probability"])
    out = dmg.rename(columns={"overture_id": "id"})[["id", "damage_probability"]].copy()
    out["damage_class"] = 2  # single "likely damaged/destroyed" class -> Damaged
    out["ems_grade"] = "Damaged"
    sp = settings.blob_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "building_damage.parquet")
    stratus.upload_parquet_to_blob(
        out, sp, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {sp} ({len(out):,} OSU-damaged buildings, id-keyed to Overture)", flush=True)

    # analyzed-area polygon -> analysed_extent.parquet (the coverage extent).
    aoi = _read_gpkg(settings, AOI_GPKG)[["geometry"]].copy()
    aoi["source"] = SOURCE
    fpath = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    stratus.upload_parquet_to_blob(
        aoi, fpath, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {fpath} (analyzed-area polygon)", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "OSU S1 coherence damage joined to Overture (id-keyed) + analyzed-area extent",
        sp,
        f"{len(out):,} damaged buildings (damage_class 2 + damage_probability); "
        "analysed extent = analyzed-area polygon",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
