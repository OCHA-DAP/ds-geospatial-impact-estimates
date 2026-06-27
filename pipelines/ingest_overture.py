"""Ingest the Overture buildings exposure base for the event extents -> silver.

The common-model comparison needs one consistent building base covering every
damage source's area (the exposure-base idea in ADR-0001). Overture buildings
(Microsoft ML + Google Open Buildings + OSM, deduped) is global, GeoParquet, and
DuckDB-queryable. We pull only the bboxes where we actually have a damage signal
— the Microsoft footprint extent + each delivered CEMS AOI.

Built for a flaky remote scan + large writes: each region is fetched and written
to its own small silver partition, with retries and skip-if-present, so the job
is idempotent and a re-run only does what's missing.

Run: uv run --group etl python pipelines/ingest_overture.py
"""

from __future__ import annotations

import time

import geopandas as gpd
import ocha_stratus as stratus

from gie import db, ledger
from gie.config import load_settings

OVERTURE = (
    "s3://overturemaps-us-west-2/release/2026-06-17.0/"
    "theme=buildings/type=building/*.parquet"
)
ADM0 = "VE"
STAGE = "dev"


def _affected_adm1_bboxes(con, settings) -> list[tuple[str, float, float, float, float]]:
    """(adm1_name, xmin, xmax, ymin, ymax) for every admin-1 state with damage.

    Pulling Overture for the *full state extent* (not per-AOI) gives a stable,
    complete building count for every affected admin unit — the correct
    denominator for coverage and extrapolation. Keyed to affected adm1 so the
    base does not shift as new AOIs deliver within the same states.
    """
    gold = settings.az_path("gold", "source=*", f"adm0={ADM0}", "damage_facts.parquet")
    adm1 = settings.az_path("bronze", "source=codab", f"adm0={ADM0}", "adm1.parquet")
    rows = con.execute(
        f"""
        WITH affected AS (
            SELECT DISTINCT unit_id AS adm1_id
            FROM read_parquet('{gold}', hive_partitioning=true) WHERE unit_type='adm1'
        )
        SELECT a.adm1_name,
               ST_XMin(a.geometry), ST_XMax(a.geometry),
               ST_YMin(a.geometry), ST_YMax(a.geometry)
        FROM read_parquet('{adm1}') a JOIN affected USING (adm1_id)
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


def main() -> None:
    settings = load_settings(STAGE)
    con = db.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    container = stratus.get_container_client(stage=STAGE, container_name=settings.container)

    total = 0
    chunk = 150_000  # keep each blob upload small enough to survive a flaky network
    for label, x0, x1, y0, y1 in _affected_adm1_bboxes(con, settings):
        region = label.strip().lower().replace(" ", "_")

        def part_path(i: int, region: str = region) -> str:
            return settings.blob_path(
                "silver", "source=overture", f"adm0={ADM0}", f"region={region}", f"part-{i}.parquet"
            )

        if container.get_blob_client(part_path(0)).exists():
            print(f"  {label}: already present, skip", flush=True)
            continue
        t = time.time()
        d = con.execute(
            f"SELECT id, geometry FROM read_parquet('{OVERTURE}', hive_partitioning=1) "
            f"WHERE bbox.xmin BETWEEN {x0} AND {x1} AND bbox.ymin BETWEEN {y0} AND {y1}"
        ).df()
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
        "Overture buildings exposure base (event extents)",
        settings.blob_path("silver", "source=overture", f"adm0={ADM0}"),
        f"~{total:,} buildings this run; release 2026-06-17.0; partitioned by region",
    )


if __name__ == "__main__":
    main()
