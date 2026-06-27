"""Common-model harmonization: project every source onto the Overture base.

The end-state of the harmonization model (ADR-0001): one shared exposure base
(Overture buildings) onto which each damage source is projected, so all sources
read in the same units. A base building is counted as damaged for a source if it
intersects that source's damage geometry:

  * Microsoft  -> intersects an MS footprint flagged damaged (binary)
  * Copernicus -> intersects a CEMS damage-grade polygon

Coverage-aware (a source may only assess part of a unit — CEMS imagery/cloud):

  exposed_buildings    base buildings in the unit
  analysed_buildings   base buildings the source could actually assess
                       (MS: all; CEMS: inside the AOI - not-analysed extent)
  coverage_fraction    analysed / exposed  (how much of the unit was seen)
  damaged_detected     damaged base buildings in the analysed area (a floor)
  damaged_extrapolated (detected / analysed) * exposed  (observed rate applied
                       to the whole unit; NULL where coverage is zero)

Extrapolation assumes damage is spatially uniform — an estimate, not a
measurement; the viewer should gate/flag it on coverage_fraction.

Output: gold/model=common — a long fact table for cross-source comparison.

Run: uv run --group etl python pipelines/harmonize_common.py
"""

from __future__ import annotations

import ocha_stratus as stratus
import pandas as pd

from gie import db, ledger
from gie.config import DEFAULT_H3_RESOLUTION, load_settings

METHOD = "common_overture_v1"
ADM0 = "VE"
STAGE = "dev"

# (source, damaged-flag, analysed-buildings expression). Each source only
# "analysed" within its own extent — MS within its footprint coverage, CEMS
# within imageFootprint - notAnalysed. Outside that, the source has no data
# (coverage 0), which is different from "assessed and found no damage".
SOURCES = [
    ("microsoft", "ms_dmg", "sum(ms_analysed::INT)"),
    ("copernicus_ems", "cems_dmg", "sum(cems_analysed::INT)"),
]
GRAINS = [
    ("h3", "h3", None),
    ("adm0", "adm0_id", "adm0_name"),
    ("adm1", "adm1_id", "adm1_name"),
    ("adm2", "adm2_id", "adm2_name"),
    ("adm3", "adm3_id", "adm3_name"),
]
METRICS = (
    "exposed_buildings, analysed_buildings, coverage_fraction, "
    "damaged_detected, damaged_extrapolated"
)


def build_facts(res: int = DEFAULT_H3_RESOLUTION) -> pd.DataFrame:
    settings = load_settings(STAGE)
    con = db.connect()
    base = settings.az_path(
        "silver", "source=overture", f"adm0={ADM0}", "region=*", "*.parquet"
    )
    ms = settings.az_path("silver", "source=microsoft", f"adm0={ADM0}", "footprints.parquet")
    cems = settings.az_path(
        "silver", "source=copernicus_ems", f"adm0={ADM0}", "builtup_damage.parquet"
    )
    analysed = settings.az_path(
        "silver", "source=copernicus_ems", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    adm3 = settings.az_path("bronze", "source=codab", f"adm0={ADM0}", "adm3.parquet")

    con.execute(
        f"""
        CREATE TEMP TABLE located AS
        WITH base AS (
            -- dedup by building id: adm1 pulls overlap each other and the old
            -- per-AOI pulls, so the same Overture building appears in >1 region
            SELECT id, geometry AS geom, ST_Centroid(geometry) AS c
            FROM read_parquet('{base}', hive_partitioning=true)
            QUALIFY row_number() OVER (PARTITION BY id) = 1
        ),
        ms_dmg AS (
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{ms}') m ON ST_Intersects(b.geom, m.geometry)
            WHERE m.damaged = 1
        ),
        cems_dmg AS (
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{cems}') x ON ST_Intersects(b.geom, x.geometry)
        ),
        cems_seen AS (
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{analysed}') e ON ST_Intersects(b.geom, e.geometry)
        ),
        ms_bbox AS (
            SELECT min(ST_XMin(geometry)) x0, max(ST_XMax(geometry)) x1,
                   min(ST_YMin(geometry)) y0, max(ST_YMax(geometry)) y1
            FROM read_parquet('{ms}')
        ),
        ms_seen AS (
            -- MS only assessed within its footprint extent (Catia La Mar);
            -- elsewhere it has no data, not "zero damage".
            SELECT b.id FROM base b, ms_bbox
            WHERE ST_X(b.c) BETWEEN x0 AND x1 AND ST_Y(b.c) BETWEEN y0 AND y1
        )
        SELECT b.id,
            h3_h3_to_string(h3_latlng_to_cell(ST_Y(b.c), ST_X(b.c), {res})) AS h3,
            a.adm0_id, a.adm0_name, a.adm1_id, a.adm1_name,
            a.adm2_id, a.adm2_name, a.adm3_id, a.adm3_name,
            (b.id IN (SELECT id FROM ms_dmg)) AS ms_dmg,
            (b.id IN (SELECT id FROM ms_seen)) AS ms_analysed,
            (b.id IN (SELECT id FROM cems_dmg)) AS cems_dmg,
            (b.id IN (SELECT id FROM cems_seen)) AS cems_analysed
        FROM base b
        LEFT JOIN read_parquet('{adm3}') a ON ST_Within(b.c, a.geometry)
        """
    )

    selects = []
    for src, flag, analysed_expr in SOURCES:
        for unit_type, idcol, namecol in GRAINS:
            name_expr = "NULL" if namecol is None else f"any_value({namecol})"
            where = "" if unit_type == "h3" else f"WHERE {idcol} IS NOT NULL"
            selects.append(
                f"""
                SELECT '{src}' AS source, '{METHOD}' AS method, '{unit_type}' AS unit_type,
                       {idcol} AS unit_id, {name_expr} AS unit_name,
                       count(*)::DOUBLE AS exposed_buildings,
                       ({analysed_expr})::DOUBLE AS analysed_buildings,
                       ({analysed_expr}) * 1.0 / count(*) AS coverage_fraction,
                       sum({flag}::INT)::DOUBLE AS damaged_detected,
                       CASE WHEN ({analysed_expr}) >= 0.25 * count(*)
                            THEN sum({flag}::INT) * 1.0 / ({analysed_expr}) * count(*)
                            ELSE NULL END AS damaged_extrapolated
                FROM located {where} GROUP BY {idcol}
                """
            )
    union = "\n        UNION ALL\n".join(selects)
    df = con.execute(
        f"""
        SELECT source, method, unit_type, unit_id, unit_name, metric, value
        FROM ( {union} )
        UNPIVOT INCLUDE NULLS (value FOR metric IN ({METRICS}))
        """
    ).df()
    df["ingested_at"] = pd.Timestamp.now("UTC")

    # Persist per-building damage/coverage flags for the building-level viewer
    # layer (geometry stays in the Overture silver; we join by id at serve time).
    flags = con.execute(
        "SELECT id, ms_dmg, ms_analysed, cems_dmg, cems_analysed FROM located"
    ).df()
    fpath = settings.blob_path("gold", "model=common", f"adm0={ADM0}", "building_flags.parquet")
    stratus.upload_parquet_to_blob(
        flags, fpath, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"building_flags <- {fpath} ({len(flags):,} buildings)")

    return df


def main() -> None:
    settings = load_settings(STAGE)
    df = build_facts()

    # Sanity: CEMS coverage + detected vs extrapolated at adm3 (where it has data).
    w = df[df.unit_type == "adm3"].pivot_table(
        index=["source", "unit_name"], columns="metric", values="value"
    )
    cems = w.loc["copernicus_ems"]
    cems = cems[cems["damaged_detected"] > 0].sort_values("damaged_detected", ascending=False)
    print("CEMS adm3 — coverage shrinks detected; extrapolation lifts it to full unit:")
    print(
        cems[
            ["exposed_buildings", "coverage_fraction", "damaged_detected", "damaged_extrapolated"]
        ].round(2).head(6).to_string()
    )

    gold = settings.blob_path("gold", "model=common", f"adm0={ADM0}", "facts.parquet")
    stratus.upload_parquet_to_blob(
        df, gold, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"gold <- {gold} ({len(df):,} fact rows)")
    ledger.record(
        "common",
        "gold",
        "Common-model damage facts (Overture base, coverage-aware)",
        gold,
        f"{len(df):,} rows; exposed/analysed/coverage/detected/extrapolated per source",
    )


if __name__ == "__main__":
    main()
