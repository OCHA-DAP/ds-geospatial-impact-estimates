"""Harmonize Copernicus EMS damage grading into the gold fact table.

Reads the graded built-up damage from the live GRA products for activation
EMSR884 — `builtUpA` (coarse damage *areas*, the early estimate) and `builtUpP`
(per-building damage *points*, the detailed update) — standardizes them to
silver tagged by `layer_type` and product version, and aggregates the latest per
AOI to the H3 grid + CODAB admin levels as a second `source` (`copernicus_ems`)
in the *same* long fact-table schema as Microsoft. Which products are live (and
which is latest) comes from `gie.cems_products`.

This is the damage-signal side of the harmonization model (ADR-0001). CEMS maps
damaged building blocks, not an exposure inventory, so its native metrics are
`damage_features` (count) and `damaged_area_m2` — carried alongside Microsoft's
building counts rather than forced into them. The EMS grade is mapped to an
xBD-style class where possible and also kept verbatim.

Run: uv run --group etl python pipelines/harmonize_cems.py
"""

from __future__ import annotations

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

from gie import db, events, ledger
from gie.cems_products import active_products, read_layer
from gie.config import DEFAULT_H3_RESOLUTION, load_settings

ACTIVATION = "EMSR884"
SOURCE = "copernicus_ems"
METHOD = "cems_grading_v1"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()

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
    """Read the graded built-up damage from each live product's GRA zip.

    CEMS grades built-up damage two ways: ``builtUpA`` (damage *areas* — the
    coarse early estimate) and ``builtUpP`` (per-building *points* — the detailed
    update that lands later). A product carries one; we keep whichever it has,
    tagged with ``layer_type`` and the product's metadata (incl. ``is_latest``),
    so downstream can attribute from the latest per AOI and still break down by
    product. Superseded versions are already excluded by ``active_products``.
    """
    products = active_products(settings, ACTIVATION, event=EVENT, stage=STAGE)
    products = products[products["product_type"] == "GRA"]
    bronze = settings.blob_path("bronze", f"source={SOURCE}", f"code={ACTIVATION}", event=EVENT)
    zip_by_name = {
        b.split("/")[-1]: b
        for b in stratus.list_container_blobs(
            name_starts_with=bronze, stage=STAGE, container_name=settings.container
        )
        if b.endswith(".zip")
    }

    parts = []
    for p in products.itertuples():
        blob = zip_by_name.get(p.zip_name)
        if blob is None:
            continue
        data = stratus.load_blob_data(blob, stage=STAGE, container_name=settings.container)
        for suffix, layer_type in (("builtUpA", "area"), ("builtUpP", "point")):
            g = read_layer(data, suffix)
            if g is None or len(g) == 0 or "damage_gra" not in g.columns:
                continue
            keep = g[["damage_gra", "geometry"]].copy()
            keep["obj_type"] = g["obj_type"] if "obj_type" in g.columns else None
            keep["aoi_number"] = int(p.aoi_number)
            keep["aoi_name"] = p.aoi_name
            keep["product_id"] = int(p.product_id)
            keep["monitoring_number"] = int(p.monitoring_number)
            keep["version_number"] = int(p.version_number)
            keep["is_latest"] = bool(p.is_latest)
            keep["layer_type"] = layer_type
            parts.append(keep)

    gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
    gdf["ems_grade"] = gdf["damage_gra"]
    gdf["damage_class"] = gdf["ems_grade"].map(
        lambda v: EMS_TO_CLASS.get(str(v).strip().lower())
    )
    # Area is meaningful only for the polygon (builtUpA) layer; points get 0.
    gdf["area_m2"] = 0.0
    poly = gdf.geom_type.isin(["Polygon", "MultiPolygon"])
    if poly.any():
        gdf.loc[poly, "area_m2"] = gdf.loc[poly].to_crs(32619).area  # UTM 19N coast
    gdf = gdf[
        [
            "aoi_number", "aoi_name", "product_id", "monitoring_number",
            "version_number", "is_latest", "layer_type", "obj_type",
            "ems_grade", "damage_class", "area_m2", "geometry",
        ]
    ]

    silver = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "builtup_damage.parquet", event=EVENT
    )
    stratus.upload_parquet_to_blob(
        gdf, silver, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    by_type = gdf.groupby("layer_type").size().to_dict()
    print(f"silver <- {silver} ({len(gdf)} graded features by layer {by_type})")
    ledger.record(
        SOURCE,
        "silver",
        f"CEMS {ACTIVATION} damage grading (builtUpA areas + builtUpP points)",
        silver,
        f"{len(gdf)} graded features; layer_type + is_latest + version; EPSG:4326",
        status="ingesting",
    )


def build_gold(settings, res: int = DEFAULT_H3_RESOLUTION) -> None:
    con = db.connect()
    sp = settings.az_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "builtup_damage.parquet", event=EVENT
    )
    # event=None: CODAB is shared, country-keyed REFERENCE data outside the
    # event tree — reusable across events (spec §3).
    adm3 = settings.az_path("bronze", "source=codab", f"adm0={ADM0}", "adm3.parquet", event=None)
    metrics = "count(*)::DOUBLE AS damage_features, sum(area_m2) AS damaged_area_m2"
    admin_unions = "\n        UNION ALL\n        ".join(
        f"SELECT '{lvl}', {lvl}_id, any_value({lvl}_name), "
        f"count(*)::DOUBLE, sum(area_m2) "
        f"FROM joined WHERE {lvl}_id IS NOT NULL GROUP BY {lvl}_id"
        for lvl in ("adm0", "adm1", "adm2", "adm3")
    )
    sql = f"""
    WITH pts AS (
        -- native CEMS view = the latest product per AOI (points where available,
        -- else coarse areas); ST_Centroid is a no-op for the point layer.
        SELECT area_m2, ST_Centroid(geometry) AS c
        FROM read_parquet('{sp}') WHERE is_latest
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

    gold = settings.blob_path(
        "gold", f"source={SOURCE}", f"adm0={ADM0}", "damage_facts.parquet", event=EVENT
    )
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
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    build_silver(settings)
    build_gold(settings)


if __name__ == "__main__":
    main()
