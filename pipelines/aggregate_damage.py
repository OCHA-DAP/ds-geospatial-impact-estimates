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

from gie import db, events, ledger
from gie.config import DEFAULT_H3_RESOLUTION, load_settings

SOURCE = "microsoft"
METHOD = "binary_damage_v1"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()


def build_facts(res: int = DEFAULT_H3_RESOLUTION) -> pd.DataFrame:
    settings = load_settings(STAGE)
    con = db.connect()
    fp = settings.az_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "footprints.parquet", event=EVENT)
    # event=None: CODAB is shared, country-keyed REFERENCE data outside the
    # event tree — reusable across events (spec §3).
    adm3 = settings.az_path("bronze", "source=codab", f"adm0={ADM0}", "adm3.parquet", event=None)

    metrics = (
        "count(*)::DOUBLE AS buildings_total, "
        "sum(damaged)::DOUBLE AS buildings_damaged, "
        "sum(damaged) * 1.0 / count(*) AS damaged_fraction, "
        "avg(damage_pct_10m) AS damage_pct_mean"
    )
    # One spatial join to adm3 yields every admin level via adm3's parent ids.
    admin_unions = "\n        UNION ALL\n        ".join(
        f"SELECT '{lvl}', {lvl}_id, any_value({lvl}_name), "
        "count(*)::DOUBLE, sum(damaged)::DOUBLE, "
        "sum(damaged) * 1.0 / count(*), avg(damage_pct_10m) "
        f"FROM joined WHERE {lvl}_id IS NOT NULL GROUP BY {lvl}_id"
        for lvl in ("adm0", "adm1", "adm2", "adm3")
    )
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
        SELECT p.damaged, p.damage_pct_10m, p.h3,
               a.adm0_id, a.adm0_name, a.adm1_id, a.adm1_name,
               a.adm2_id, a.adm2_name, a.adm3_id, a.adm3_name
        FROM cells p
        LEFT JOIN read_parquet('{adm3}') a ON ST_Within(p.c, a.geometry)
    ),
    agg AS (
        SELECT 'h3' AS unit_type, h3 AS unit_id, NULL AS unit_name,
               {metrics}
        FROM joined GROUP BY h3
        UNION ALL
        {admin_unions}
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
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    df = build_facts()

    # Quick sanity summary.
    n_h3 = df[df.unit_type == "h3"].unit_id.nunique()
    counts = {
        lvl: df[df.unit_type == lvl].unit_id.nunique()
        for lvl in ("adm0", "adm1", "adm2", "adm3")
    }
    adm3 = (
        df[(df.unit_type == "adm3") & (df.metric == "buildings_total")]
        .sort_values("value", ascending=False)
    )
    print(f"facts rows={len(df):,} | h3 cells={n_h3} | units {counts}")
    print("adm3 by buildings:")
    for _, r in adm3.iterrows():
        print(f"  {r.unit_name} ({r.unit_id}): {int(r.value):,}")

    gold = settings.blob_path(
        "gold", f"source={SOURCE}", f"adm0={ADM0}", "damage_facts.parquet", event=EVENT
    )
    stratus.upload_parquet_to_blob(
        df, gold, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"gold <- {gold}")

    ledger.record(
        source=SOURCE,
        layer="gold",
        dataset="Damage facts — Catia La Mar",
        path=gold,
        detail=f"{len(df):,} fact rows; h3 + adm0-3; metrics buildings/damaged/fraction",
    )


if __name__ == "__main__":
    main()
