"""Gold aggregation: Microsoft footprints -> H3 + admin damage-fact table.

Reads the silver footprints and CODAB adm2 directly from blob (cloud-optimized),
assigns each building to an H3 cell and an admin-2 unit by its centroid, and
emits the canonical long damage-fact table (ADR-0001) at both grains:

    source | method | unit_type (h3|adm2) | unit_id | unit_name | metric | value

Metrics: buildings_total, buildings_damaged, damaged_fraction, damage_pct_mean.
Both spike front ends consume this one gold table. Written to blob via stratus
(periodic ETL write, not the hot read path; see docs/decisions/0003).

Run: uv run --group etl python pipelines/aggregate_damage.py
"""

from __future__ import annotations

import ocha_stratus as stratus
import pandas as pd

from gie import db
from gie.config import DEFAULT_H3_RESOLUTION, load_settings

SOURCE = "microsoft"
METHOD = "binary_damage_v1"
ADM0 = "VE"
STAGE = "dev"


def build_facts(res: int = DEFAULT_H3_RESOLUTION) -> pd.DataFrame:
    settings = load_settings(STAGE)
    con = db.connect()
    fp = settings.az_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "footprints.parquet")
    adm2 = settings.az_path("bronze", "source=codab", f"adm0={ADM0}", "adm2.parquet")

    sql = f"""
    WITH pts AS (
        SELECT damaged, damage_pct_10m, ST_Centroid(geometry) AS c
        FROM read_parquet('{fp}')
    ),
    cells AS (
        SELECT damaged, damage_pct_10m, c,
               h3_h3_to_string(h3_latlng_to_cell(ST_Y(c), ST_X(c), {res})) AS h3
        FROM pts
    ),
    joined AS (
        SELECT p.damaged, p.damage_pct_10m, p.h3, a.adm2_id, a.adm2_name
        FROM cells p
        LEFT JOIN read_parquet('{adm2}') a ON ST_Within(p.c, a.geometry)
    ),
    agg AS (
        SELECT 'h3' AS unit_type, h3 AS unit_id, NULL AS unit_name,
               count(*)::DOUBLE AS buildings_total,
               sum(damaged)::DOUBLE AS buildings_damaged,
               sum(damaged) * 1.0 / count(*) AS damaged_fraction,
               avg(damage_pct_10m) AS damage_pct_mean
        FROM joined GROUP BY h3
        UNION ALL
        SELECT 'adm2', adm2_id, any_value(adm2_name),
               count(*)::DOUBLE, sum(damaged)::DOUBLE,
               sum(damaged) * 1.0 / count(*), avg(damage_pct_10m)
        FROM joined WHERE adm2_id IS NOT NULL GROUP BY adm2_id
    )
    SELECT '{SOURCE}' AS source, '{METHOD}' AS method,
           unit_type, unit_id, unit_name, metric, value
    FROM (
        SELECT * FROM agg
        UNPIVOT (value FOR metric IN
            (buildings_total, buildings_damaged, damaged_fraction, damage_pct_mean))
    )
    """
    df = con.execute(sql).df()
    df["ingested_at"] = pd.Timestamp.now("UTC")
    return df


def main() -> None:
    settings = load_settings(STAGE)
    df = build_facts()

    # Quick sanity summary.
    n_h3 = df[df.unit_type == "h3"].unit_id.nunique()
    adm2 = (
        df[(df.unit_type == "adm2") & (df.metric == "buildings_total")]
        .sort_values("value", ascending=False)
    )
    print(f"facts rows={len(df):,} | h3 cells={n_h3} | adm2 units={len(adm2)}")
    print("top adm2 by buildings:")
    for _, r in adm2.head(3).iterrows():
        print(f"  {r.unit_name} ({r.unit_id}): {int(r.value):,}")

    gold = settings.blob_path("gold", f"source={SOURCE}", f"adm0={ADM0}", "damage_facts.parquet")
    stratus.upload_parquet_to_blob(
        df, gold, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"gold <- {gold}")


if __name__ == "__main__":
    main()
