"""Harmonize Copernicus EMS damage grading into the gold fact table.

Reads the delivered GRA `builtUpA` layers (damage-graded built-up-area polygons,
each with an EMS damage grade) for activation EMSR884, standardizes them to
silver, and aggregates to the H3 grid + CODAB admin levels as a second `source`
(`copernicus_ems`) in the *same* long fact-table schema as Microsoft.

This is the damage-signal side of the harmonization model (ADR-0001). CEMS maps
damaged building blocks, not an exposure inventory, so its native metrics are
`damage_features` (count) and `damaged_area_m2` — carried alongside Microsoft's
building counts rather than forced into them. The EMS grade is mapped to an
xBD-style class where possible and also kept verbatim.

Run: uv run --group etl python pipelines/harmonize_cems.py
"""

from __future__ import annotations

import geopandas as gpd
import ocha_lens as lens
import ocha_stratus as stratus
import pandas as pd

from gie import db, ledger
from gie.config import DEFAULT_H3_RESOLUTION, load_settings

ACTIVATION = "EMSR884"
SOURCE = "copernicus_ems"
METHOD = "cems_grading_v1"
ADM0 = "VE"
STAGE = "dev"

# Copernicus EMS damage grade -> xBD-style class (0..3). Raw grade kept too.
EMS_TO_CLASS = {
    "destroyed": 3,
    "completely destroyed": 3,
    "highly damaged": 3,
    "moderately damaged": 2,
    "damaged": 2,
    "possibly damaged": 1,
    "negligible to slight damage": 0,
    "not affected": 0,
}


def build_silver(settings) -> None:
    cat = lens.cems.get_catalog(ACTIVATION)
    built = cat[cat.layer_name.str.contains("builtUpA") & cat.geojson_url.notna()]
    parts = []
    for _, row in built.iterrows():
        g = lens.cems.download_geojson(row)
        if g is None or len(g) == 0:
            continue
        g = g.to_crs(4326)
        g["aoi_number"] = int(row.aoi_number)
        g["aoi_name"] = row.aoi_name
        parts.append(g)

    gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
    gdf["ems_grade"] = gdf["damage_gra"]
    gdf["damage_class"] = gdf["ems_grade"].map(
        lambda v: EMS_TO_CLASS.get(str(v).strip().lower())
    )
    gdf["area_m2"] = gdf.to_crs(32619).area  # UTM 19N for the Venezuela coast
    gdf = gdf[
        ["aoi_number", "aoi_name", "obj_type", "ems_grade", "damage_class", "area_m2", "geometry"]
    ]

    silver = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "builtup_damage.parquet"
    )
    stratus.upload_parquet_to_blob(
        gdf, silver, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    grades = sorted(gdf["ems_grade"].dropna().unique().tolist())
    print(f"silver <- {silver} ({len(gdf)} graded blocks; grades {grades})")
    ledger.record(
        SOURCE,
        "silver",
        f"CEMS {ACTIVATION} damage grading (builtUpA)",
        silver,
        f"{len(gdf)} graded blocks; EMS grade + class; EPSG:4326",
        status="ingesting",
    )


def build_gold(settings, res: int = DEFAULT_H3_RESOLUTION) -> None:
    con = db.connect()
    sp = settings.az_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "builtup_damage.parquet")
    adm3 = settings.az_path("bronze", "source=codab", f"adm0={ADM0}", "adm3.parquet")
    metrics = "count(*)::DOUBLE AS damage_features, sum(area_m2) AS damaged_area_m2"
    admin_unions = "\n        UNION ALL\n        ".join(
        f"SELECT '{lvl}', {lvl}_id, any_value({lvl}_name), "
        f"count(*)::DOUBLE, sum(area_m2) "
        f"FROM joined WHERE {lvl}_id IS NOT NULL GROUP BY {lvl}_id"
        for lvl in ("adm0", "adm1", "adm2", "adm3")
    )
    sql = f"""
    WITH pts AS (
        SELECT area_m2, ST_Centroid(geometry) AS c FROM read_parquet('{sp}')
    ),
    cells AS (
        SELECT area_m2, c,
               h3_h3_to_string(h3_latlng_to_cell(ST_Y(c), ST_X(c), {res})) AS h3
        FROM pts
    ),
    joined AS (
        SELECT p.area_m2, p.h3,
               a.adm0_id, a.adm0_name, a.adm1_id, a.adm1_name,
               a.adm2_id, a.adm2_name, a.adm3_id, a.adm3_name
        FROM cells p
        LEFT JOIN read_parquet('{adm3}') a ON ST_Within(p.c, a.geometry)
    ),
    agg AS (
        SELECT 'h3' AS unit_type, h3 AS unit_id, NULL AS unit_name, {metrics}
        FROM joined GROUP BY h3
        UNION ALL
        {admin_unions}
    )
    SELECT '{SOURCE}' AS source, '{METHOD}' AS method,
           unit_type, unit_id, unit_name, metric, value
    FROM (
        SELECT * FROM agg
        UNPIVOT (value FOR metric IN (damage_features, damaged_area_m2))
    )
    """
    out = con.execute(sql).df()
    out["ingested_at"] = pd.Timestamp.now("UTC")

    gold = settings.blob_path("gold", f"source={SOURCE}", f"adm0={ADM0}", "damage_facts.parquet")
    stratus.upload_parquet_to_blob(
        out, gold, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    by_adm3 = out[(out.unit_type == "adm3") & (out.metric == "damage_features")]
    print(f"gold <- {gold} ({len(out)} facts; adm3 units with CEMS damage: {len(by_adm3)})")
    print(by_adm3[["unit_name", "value"]].to_string(index=False))
    ledger.record(
        SOURCE,
        "gold",
        f"CEMS {ACTIVATION} damage facts",
        gold,
        f"{len(out)} fact rows; h3 + adm0-3; damage_features + damaged_area_m2",
        status="ingesting",
    )


def main() -> None:
    settings = load_settings(STAGE)
    build_silver(settings)
    build_gold(settings)


if __name__ == "__main__":
    main()
