"""Ingest the Overture buildings exposure base for the event extents -> silver.

Registry-driven, one event per run: ``--event <event_id>`` (ADR-0027; same
pattern as ingest_cems). The common-model comparison needs one consistent
building base covering every damage source's area (the exposure-base idea in
ADR-0001). Overture buildings (Microsoft ML + Google Open Buildings + OSM,
deduped) is global, GeoParquet, and DuckDB-queryable. We pull the full extent
of every admin-1 state that any source's coverage intersects, so
total-building counts are complete for every admin unit inside those states
(the denominator for coverage and rates).

Built for a flaky remote scan + large writes: each state is fetched and written
to its own silver partition in 150k-row chunks, with retries and skip-if-present,
so the job is idempotent and a re-run only pulls states not yet present — new
coverage in a new state is picked up automatically.

Run: uv run --group etl python pipelines/ingest_overture.py --event 20260810-co-earthquake
"""

from __future__ import annotations

import argparse
import time

import geopandas as gpd
import ocha_stratus as stratus

from gie import db, events, ledger
from gie.config import load_settings, source_segments

OVERTURE = (
    "s3://overturemaps-us-west-2/release/2026-06-17.0/"
    "theme=buildings/type=building/*.parquet"
)
STAGE = "dev"
# Sources that publish an analysed extent (coverage) — the union bounds the base.
EXTENT_SOURCES = ["copernicus_ems", "microsoft", "impact_initiatives", "osu"]


def _affected_adm1_bboxes(con, settings, ev) -> list[tuple[str, float, float, float, float]]:
    """(adm1_name, xmin, xmax, ymin, ymax) for every admin-1 state that any
    source's coverage intersects.

    The rule: if a source's analysed extent touches an admin-1 state at all, pull
    that whole state's Overture base, so total-building counts are complete for
    every admin unit inside it. Driven by the coverage geometries (CEMS
    analysed swaths + Microsoft masks), NOT by the gold/existing base — so it is
    non-circular and picks up new states automatically as coverage is added.
    """
    # Union EVERY source's analysed_extent (coverage), so the base covers any state
    # any source assessed. Sources without an extent file for this event are
    # skipped. New sources are picked up with no change here; the per-state pull
    # below is idempotent (skip-if-present).
    cc = stratus.get_container_client(stage=STAGE, container_name=settings.container)
    exts = [
        settings.az_path(
            "silver", *source_segments(src, ev.event_id), "analysed_extent.parquet",
            event=ev.event_id,
        )
        for src in EXTENT_SOURCES
        if cc.get_blob_client(
            settings.blob_path(
                "silver", *source_segments(src, ev.event_id), "analysed_extent.parquet",
                event=ev.event_id,
            )
        ).exists()
    ]
    if not exts:
        raise RuntimeError("no source analysed_extent found — nothing to bound the base pull")
    cov = " UNION ALL ".join(
        f"SELECT ST_MakeValid(geometry) AS g FROM read_parquet('{p}')" for p in exts
    )
    if len(ev.countries) != 1:
        raise NotImplementedError(
            f"event {ev.event_id} spans countries {ev.countries} — the adm1 bound "
            "needs a CODAB union across countries; build it deliberately."
        )
    # event=None: CODAB is shared, country-keyed REFERENCE data outside the
    # event tree — reusable across events (spec §3).
    adm1 = settings.az_path(
        "bronze", "source=codab", f"adm0={ev.countries[0]}", "adm1.parquet", event=None
    )
    # Return each affected state's bbox (for parquet pushdown) AND its polygon (WKB,
    # to clip the pull) — so we fetch the whole state's buildings (complete admin
    # denominators, ADR-0006) but not the ocean/neighbour spillover the bbox
    # rectangle would drag in.
    rows = con.execute(
        f"""
        WITH cov AS ({cov})
        SELECT a.adm1_name,
               ST_XMin(a.geometry), ST_XMax(a.geometry),
               ST_YMin(a.geometry), ST_YMax(a.geometry),
               ST_AsWKB(ST_MakeValid(a.geometry))
        FROM read_parquet('{adm1}') a
        WHERE EXISTS (SELECT 1 FROM cov WHERE ST_Intersects(a.geometry, cov.g))
        """
    ).fetchall()
    return [tuple(r) for r in rows]


def _upload(gdf, blob, settings, tries: int = 4) -> bool:
    for attempt in range(tries):
        try:
            stratus.upload_parquet_to_blob(
                gdf, blob, stage=STAGE, container_name=settings.container, compression="zstd"
            )
            return True
        except Exception as e:  # noqa: BLE001 — network write, retry any failure
            print(f"   upload retry {attempt + 1}/{tries}: {str(e)[:70]}", flush=True)
            time.sleep(3)
    return False


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event", required=True, help="event_id from events.yaml whose base to pull"
    )
    args = parser.parse_args(argv)
    ev = events.get_event(args.event)  # fails loudly on an unregistered event

    settings = load_settings(STAGE)
    con = db.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    container = stratus.get_container_client(stage=STAGE, container_name=settings.container)

    total = 0
    chunk = 150_000  # keep each blob upload small enough to survive a flaky network
    for label, x0, x1, y0, y1, wkb in _affected_adm1_bboxes(con, settings, ev):
        region = label.strip().lower().replace(" ", "_")

        def part_path(i: int, region: str = region) -> str:
            return settings.blob_path(
                "silver", *source_segments("overture", ev.event_id),
                f"region={region}", f"part-{i}.parquet",
                event=ev.event_id,
            )

        if container.get_blob_client(part_path(0)).exists():
            print(f"  {label}: already present, skip", flush=True)
            continue
        t = time.time()
        # bbox for parquet pushdown, then clip to the state polygon (drops the
        # ocean/neighbour buildings the rectangle would otherwise pull).
        d = con.execute(
            f"SELECT id, geometry FROM read_parquet('{OVERTURE}', hive_partitioning=1) "
            f"WHERE bbox.xmin BETWEEN {x0} AND {x1} AND bbox.ymin BETWEEN {y0} AND {y1} "
            f"AND ST_Intersects(geometry, ST_GeomFromWKB(?::BLOB))",
            [bytes(wkb)],
        ).df()
        if not len(d):
            print(f"  {label}: no buildings in polygon, skip", flush=True)
            continue
        geom = gpd.GeoSeries.from_wkb(d.pop("geometry").map(bytes), crs="EPSG:4326")
        gdf = gpd.GeoDataFrame(d, geometry=geom, crs="EPSG:4326")
        ok = all(
            _upload(gdf.iloc[i : i + chunk], part_path(i // chunk), settings)
            for i in range(0, len(gdf), chunk)
        )
        if not ok:
            print(f"  {label}: UPLOAD FAILED — re-run to retry this region", flush=True)
            continue
        total += len(gdf)
        dt = time.time() - t
        print(f"  {label}: {len(gdf):,} buildings -> region={region} ({dt:.0f}s)", flush=True)

    ledger.record(
        "overture",
        "silver",
        f"Overture buildings exposure base — {ev.name}",
        settings.blob_path(
            "silver", *source_segments("overture", ev.event_id), event=ev.event_id
        ),
        f"~{total:,} buildings this run; release 2026-06-17.0; partitioned by region",
    )


if __name__ == "__main__":
    main()
