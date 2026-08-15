"""Gold aggregation: Microsoft footprints -> H3 + admin damage-fact table.

Registry-driven, one event per run: ``--event <event_id>`` (ADR-0027). Reads
the silver footprints and CODAB directly from blob (cloud-optimized), assigns
each building to an H3 cell and admin units by its centroid, and emits the
canonical long damage-fact table (ADR-0001) at both grains:

    source | method | unit_type (h3|admN) | unit_id | unit_name | metric | value

Metrics: buildings_total, buildings_damaged, damaged_fraction, damage_pct_mean.
The admin rollup goes to the deepest CODAB level the event's country actually
has (VE: adm3; CO: adm2). Written to blob via stratus (periodic ETL write, not
the hot read path; see docs/decisions/0003).

Run: uv run --group etl python pipelines/aggregate_damage.py --event 20260810-co-earthquake
"""

from __future__ import annotations

import argparse

import ocha_stratus as stratus
import pandas as pd

from gie import codab, db, events, ledger
from gie.config import DEFAULT_H3_RESOLUTION, load_settings, source_segments

SOURCE = "microsoft"
METHOD = "binary_damage_v1"
STAGE = "dev"


def build_facts(
    settings, ev: events.Event, deepest: int, res: int = DEFAULT_H3_RESOLUTION
) -> pd.DataFrame:
    con = db.connect()
    fp = settings.az_path(
        "silver", *source_segments(SOURCE, ev.event_id), "footprints.parquet", event=ev.event_id
    )
    # event=None: CODAB is shared, country-keyed REFERENCE data outside the
    # event tree — reusable across events (spec §3).
    admin = settings.az_path(
        "bronze", "source=codab", f"adm0={ev.countries[0]}", f"adm{deepest}.parquet", event=None
    )
    levels = [f"adm{i}" for i in range(deepest + 1)]

    metrics = (
        "count(*)::DOUBLE AS buildings_total, "
        "sum(damaged)::DOUBLE AS buildings_damaged, "
        "sum(damaged) * 1.0 / count(*) AS damaged_fraction, "
        "avg(damage_pct_10m) AS damage_pct_mean"
    )
    # One spatial join to the deepest level yields every admin level via its parent ids.
    admin_cols = ", ".join(f"a.{lvl}_id, a.{lvl}_name" for lvl in levels)
    admin_unions = "\n        UNION ALL\n        ".join(
        f"SELECT '{lvl}', {lvl}_id, any_value({lvl}_name), "
        "count(*)::DOUBLE, sum(damaged)::DOUBLE, "
        "sum(damaged) * 1.0 / count(*), avg(damage_pct_10m) "
        f"FROM joined WHERE {lvl}_id IS NOT NULL GROUP BY {lvl}_id"
        for lvl in levels
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
        SELECT p.damaged, p.damage_pct_10m, p.h3, {admin_cols}
        FROM cells p
        LEFT JOIN read_parquet('{admin}') a ON ST_Within(p.c, a.geometry)
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event", required=True, help="event_id from events.yaml to aggregate"
    )
    args = parser.parse_args(argv)
    ev = events.get_event(args.event)  # fails loudly on an unregistered event
    if len(ev.countries) != 1:
        raise NotImplementedError(
            f"event {ev.event_id} spans countries {ev.countries} — the admin rollup "
            "needs a CODAB union across countries; build it deliberately."
        )
    settings = load_settings(STAGE)
    deepest = codab.deepest_level(settings, ev.countries[0], stage=STAGE)
    df = build_facts(settings, ev, deepest)

    # Quick sanity summary.
    n_h3 = df[df.unit_type == "h3"].unit_id.nunique()
    counts = {
        lvl: df[df.unit_type == lvl].unit_id.nunique()
        for lvl in [f"adm{i}" for i in range(deepest + 1)]
    }
    deep = (
        df[(df.unit_type == f"adm{deepest}") & (df.metric == "buildings_total")]
        .sort_values("value", ascending=False)
    )
    print(f"facts rows={len(df):,} | h3 cells={n_h3} | units {counts}")
    print(f"adm{deepest} by buildings:")
    for _, r in deep.iterrows():
        print(f"  {r.unit_name} ({r.unit_id}): {int(r.value):,}")

    gold = settings.blob_path(
        "gold", *source_segments(SOURCE, ev.event_id), "damage_facts.parquet", event=ev.event_id
    )
    stratus.upload_parquet_to_blob(
        df, gold, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"gold <- {gold}")

    ledger.record(
        source=SOURCE,
        layer="gold",
        dataset=f"Microsoft native damage facts — {ev.name}",
        path=gold,
        detail=f"{len(df):,} fact rows; h3 + adm0-{deepest}; metrics buildings/damaged/fraction",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
