"""Project the LIST ResNet change-detection damage rasters onto Overture -> silver.

LIST delivered two 10 m raster damage classifications (bronze COGs, EPSG:32618),
one per scene footprint, covering the central Venezuela coast (see
``ingest_list``). This samples them at each Overture building centroid — the same
raster-sampling approach the (now-superseded) ``harmonize_impact_sar`` used, but
via the generic primitives in ``gie.raster`` — and, like ``harmonize_osu``, emits
an id-keyed damaged set + an analysed-extent polygon (no geometry: ``id`` joins
onto the Overture base).

Class model (validated against IMPACT-v2 + OSU, not just assumed): the raster
values are {0,1,2}, but only **class 2** is a real damage signal — it is ~9x
enriched for independent cross-source damage agreement (14% corroborated vs 1.5%
background), whereas class 1 sits at the background rate (~2.5%) and is NOT
damage (built-up / generic pre-post change; ~2.5M buildings, would be false
positives). So:
    0, 1 -> analysed, not flagged
    2    -> damage_class 2  "Damaged"   (mirrors OSU's single-class treatment)
Even class 2 over-triggers (163k vs ~60-70k from peers) and scatters inland: a
preliminary change-detection SCREEN with false positives, NOT a confirmed census.
Reprocess if the provider documents a different taxonomy.

Two scenes overlap in a ~1 deg seam near 68 W; damaged ids are de-duplicated. The
analysed extent is the union of the two raster footprints (the model classified
every pixel — 0/1 mean analysed — so the footprint IS the analysed area; it
includes water, which has no buildings, so building-level coverage is unaffected).

Output (mirrors source=osu):
  * building_damage.parquet — one row per LIST-damaged building (id, damage_class,
    ems_grade). No geometry.
  * analysed_extent.parquet — union of the two scene footprints (coverage extent).

Run: uv run --group etl python pipelines/harmonize_list.py
"""

from __future__ import annotations

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd
from shapely.ops import unary_union

from gie import db, events, ledger
from gie.config import load_settings
from gie.raster import (
    open_local_or_blob,
    raster_footprint,
    raster_lonlat_bounds,
    sample_points,
)

SOURCE = "list"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()
DAMAGE_VALUE = 2  # only class 2 is real damage (validated); 0/1 = analysed, not flagged
SCENES = [
    "predicted_resnet_prepost_Venezuela_2026_filter_1_upated.tif",         # eastern
    "predicted_resnet_prepost_scene2_Venezuela_2026_filter_1_upated.tif",  # western
]


def _sample_scene(con, settings, name):
    """Return (damaged-building-id DataFrame, footprint polygon in EPSG:4326)."""
    bpath = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name, event=EVENT)
    with open_local_or_blob(settings, bpath) as path:
        west, south, east, north = raster_lonlat_bounds(path)
        base = settings.az_path(
            "silver", "source=overture", f"adm0={ADM0}", "region=*", "*.parquet", event=EVENT
        )
        df = con.execute(
            f"""
            SELECT id, ST_X(c) AS lon, ST_Y(c) AS lat FROM (
                SELECT id, ST_Centroid(geometry) AS c
                FROM read_parquet('{base}', hive_partitioning=true)
                QUALIFY row_number() OVER (PARTITION BY id) = 1
            )
            WHERE lon BETWEEN {west} AND {east} AND lat BETWEEN {south} AND {north}
            """
        ).df()
        cls = sample_points(path, df["lon"].to_numpy(), df["lat"].to_numpy())
        footprint = raster_footprint(path)
    return df.loc[cls == DAMAGE_VALUE, ["id"]], footprint


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    con = db.connect()

    ids, footprints = [], []
    for name in SCENES:
        dmg, fp = _sample_scene(con, settings, name)
        print(f"  {name}: {len(dmg):,} damaged buildings (class {DAMAGE_VALUE})", flush=True)
        ids.append(dmg)
        footprints.append(fp)

    # de-dupe damaged ids across the ~1 deg scene overlap seam.
    out = pd.concat(ids, ignore_index=True).drop_duplicates("id").reset_index(drop=True)
    out["damage_class"] = 2
    out["ems_grade"] = "Damaged"

    sp = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "building_damage.parquet", event=EVENT
    )
    stratus.upload_parquet_to_blob(
        out[["id", "damage_class", "ems_grade"]],
        sp, stage=STAGE, container_name=settings.container, compression="zstd",
    )
    print(f"silver <- {sp} ({len(out):,} LIST-damaged buildings, class 2 -> Damaged)", flush=True)

    # analysed extent = union of the two scene footprints.
    extent = unary_union(footprints)
    fp = gpd.GeoDataFrame({"source": [SOURCE]}, geometry=[extent], crs="EPSG:4326")
    fpath = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "analysed_extent.parquet", event=EVENT
    )
    stratus.upload_parquet_to_blob(
        fp, fpath, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {fpath} (union of {len(footprints)} scene footprints)", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "LIST ResNet change-detection damage sampled onto Overture (id-keyed, class 2 only) + footprint extent",
        sp,
        f"{len(out):,} damaged buildings (class 2 -> Damaged; class 1 dropped as "
        "not-damage, validated vs IMPACT/OSU); analysed extent = union of 2 scene "
        "footprints; preliminary change-detection screen, reprocess if provider differs",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
