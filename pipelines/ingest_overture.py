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


def _damage_bboxes(con, settings) -> list[tuple[str, float, float, float, float]]:
    """(label, xmin, xmax, ymin, ymax) for the MS extent and each CEMS AOI."""
    ms = settings.az_path("silver", "source=microsoft", f"adm0={ADM0}", "footprints.parquet")
    cems = settings.az_path(
        "silver", "source=copernicus_ems", f"adm0={ADM0}", "builtup_damage.parquet"
    )
    bb = (
        "min(ST_XMin(geometry)), max(ST_XMax(geometry)), "
        "min(ST_YMin(geometry)), max(ST_YMax(geometry))"
    )
    out: list[tuple[str, float, float, float, float]] = []
    row = con.execute(f"SELECT {bb} FROM read_parquet('{ms}')").fetchone()
    out.append(("microsoft", *row))
    for r in con.execute(
        f"SELECT aoi_name, {bb} FROM read_parquet('{cems}') GROUP BY aoi_name"
    ).fetchall():
        out.append((f"cems:{r[0]}", *r[1:]))
    return out


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
    for label, x0, x1, y0, y1 in _damage_bboxes(con, settings):
        region = label.split(":")[-1].strip().lower().replace(" ", "_")
        blob = settings.blob_path(
            "silver", "source=overture", f"adm0={ADM0}", f"region={region}", "buildings.parquet"
        )
        if container.get_blob_client(blob).exists():
            print(f"  {label}: already present, skip", flush=True)
            continue
        t = time.time()
        d = con.execute(
            f"SELECT id, geometry FROM read_parquet('{OVERTURE}', hive_partitioning=1) "
            f"WHERE bbox.xmin BETWEEN {x0} AND {x1} AND bbox.ymin BETWEEN {y0} AND {y1}"
        ).df()
        geom = gpd.GeoSeries.from_wkb(d.pop("geometry").map(bytes), crs="EPSG:4326")
        gdf = gpd.GeoDataFrame(d, geometry=geom, crs="EPSG:4326")
        if not _upload(gdf, blob, settings):
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
