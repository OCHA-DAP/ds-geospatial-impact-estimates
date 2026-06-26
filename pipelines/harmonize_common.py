"""Common-model harmonization: project every source onto the Overture base.

The end-state of the harmonization model (ADR-0001): one shared exposure base
(Overture buildings) onto which each damage source is projected, so all sources
read in the same units — `buildings_damaged` / `exposed_buildings` /
`damaged_fraction` per spatial unit. A base building is counted as damaged for a
source if it intersects that source's damage geometry:

  * Microsoft  -> intersects an MS footprint flagged damaged (binary)
  * Copernicus -> intersects a CEMS damage-grade polygon

Output: gold/model=common — a long fact table the viewer reads to compare
sources head-to-head on one consistent denominator.

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

SOURCES = [("microsoft", "ms_dmg"), ("copernicus_ems", "cems_dmg")]
GRAINS = [
    ("h3", "h3", None),
    ("adm0", "adm0_id", "adm0_name"),
    ("adm1", "adm1_id", "adm1_name"),
    ("adm2", "adm2_id", "adm2_name"),
    ("adm3", "adm3_id", "adm3_name"),
]


def build_facts(res: int = DEFAULT_H3_RESOLUTION) -> pd.DataFrame:
    settings = load_settings(STAGE)
    con = db.connect()
    base = settings.az_path(
        "silver", "source=overture", f"adm0={ADM0}", "region=*", "buildings.parquet"
    )
    ms = settings.az_path("silver", "source=microsoft", f"adm0={ADM0}", "footprints.parquet")
    cems = settings.az_path(
        "silver", "source=copernicus_ems", f"adm0={ADM0}", "builtup_damage.parquet"
    )
    adm3 = settings.az_path("bronze", "source=codab", f"adm0={ADM0}", "adm3.parquet")

    # One pass: locate each base building (H3 + admin) and flag damage per source.
    con.execute(
        f"""
        CREATE TEMP TABLE located AS
        WITH base AS (
            SELECT id, geometry AS geom, ST_Centroid(geometry) AS c
            FROM read_parquet('{base}', hive_partitioning=true)
        ),
        ms_dmg AS (
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{ms}') m ON ST_Intersects(b.geom, m.geometry)
            WHERE m.damaged = 1
        ),
        cems_dmg AS (
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{cems}') x ON ST_Intersects(b.geom, x.geometry)
        )
        SELECT b.id,
            h3_h3_to_string(h3_latlng_to_cell(ST_Y(b.c), ST_X(b.c), {res})) AS h3,
            a.adm0_id, a.adm0_name, a.adm1_id, a.adm1_name,
            a.adm2_id, a.adm2_name, a.adm3_id, a.adm3_name,
            (b.id IN (SELECT id FROM ms_dmg)) AS ms_dmg,
            (b.id IN (SELECT id FROM cems_dmg)) AS cems_dmg
        FROM base b
        LEFT JOIN read_parquet('{adm3}') a ON ST_Within(b.c, a.geometry)
        """
    )

    selects = []
    for src, flag in SOURCES:
        for unit_type, idcol, namecol in GRAINS:
            name_expr = "NULL" if namecol is None else f"any_value({namecol})"
            where = "" if unit_type == "h3" else f"WHERE {idcol} IS NOT NULL"
            selects.append(
                f"""
                SELECT '{src}' AS source, '{METHOD}' AS method, '{unit_type}' AS unit_type,
                       {idcol} AS unit_id, {name_expr} AS unit_name,
                       count(*)::DOUBLE AS exposed_buildings,
                       sum({flag}::INT)::DOUBLE AS damaged_buildings,
                       sum({flag}::INT) * 1.0 / count(*) AS damaged_fraction
                FROM located {where} GROUP BY {idcol}
                """
            )
    union = "\n        UNION ALL\n".join(selects)
    df = con.execute(
        f"""
        SELECT source, method, unit_type, unit_id, unit_name, metric, value
        FROM ( {union} )
        UNPIVOT (value FOR metric IN (exposed_buildings, damaged_buildings, damaged_fraction))
        """
    ).df()
    df["ingested_at"] = pd.Timestamp.now("UTC")
    return df


def main() -> None:
    settings = load_settings(STAGE)
    df = build_facts()

    # Sanity: damaged buildings per source at adm3 (the comparison shape).
    adm3 = df[(df.unit_type == "adm3") & (df.metric == "damaged_buildings") & (df.value > 0)]
    summary = adm3.groupby("source").agg(units=("unit_id", "nunique"), damaged=("value", "sum"))
    print("damaged buildings on the common Overture base, by source (adm3):")
    print(summary.to_string())

    gold = settings.blob_path("gold", "model=common", f"adm0={ADM0}", "facts.parquet")
    stratus.upload_parquet_to_blob(
        df, gold, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"gold <- {gold} ({len(df):,} fact rows)")
    ledger.record(
        "common",
        "gold",
        "Common-model damage facts (Overture base)",
        gold,
        f"{len(df):,} rows; sources MS + CEMS on Overture base; exposed/damaged/fraction",
    )


if __name__ == "__main__":
    main()
