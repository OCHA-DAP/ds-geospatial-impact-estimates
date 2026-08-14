"""Normalize the UNEP/OCHA JEU building-debris assessment (bronze) -> silver.

The debris product reports building **debris MASS (tonnes)** per damaged building,
on a Global Building Atlas footprint base. Unlike the graded damage sources
(Microsoft / CEMS / HOT), it carries **no damage class or grade** — the metric *is*
the mass — and it ships **no analysed extent**, so it is **detected-only** in the
common model. It is also SAR-derived and independent of our other sources, not a
fusion of them (see `exploratory/0003` and the fusion analysis).

Output: `debris.parquet` — one row per damaged building (`fid` + `debris_tonnes` +
footprint). The buildings are NOT snapped to the Overture base here; like the CEMS
and HOT points, that join happens in `harmonize_common` (the only place that scans
the base), by building centroid. Because native footprints (GBA) are finer than
Overture, the snapped count is materially below this native count — reported on two
bases per [ADR-0017](../docs/decisions/0017-source-counts-two-bases-snapped-vs-native.md).

Run: uv run --group etl python pipelines/harmonize_debris.py
"""

from __future__ import annotations

import tempfile

import geopandas as gpd
import ocha_stratus as stratus

from gie import events, ledger
from gie.config import load_settings

SOURCE = "unep_debris"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()
RESOURCE = "debris_buildings.gpkg"


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)

    bronze = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", RESOURCE, event=EVENT)
    raw = stratus.load_blob_data(bronze, stage=STAGE, container_name=settings.container)
    with tempfile.NamedTemporaryFile(suffix=".gpkg") as tf:
        tf.write(raw)
        tf.flush()
        gdf = gpd.read_file(tf.name).to_crs(4326)

    # A stable per-building key for the base snap in harmonize_common (partition key,
    # mirroring the generated fid the HOT/CEMS point snaps use); the gpkg's own fid is
    # engine-dependent, so we assign our own.
    out = gdf[["debris", "geometry"]].rename(columns={"debris": "debris_tonnes"})
    out = out.reset_index(drop=True)
    out.insert(0, "fid", out.index)

    silver = settings.blob_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "debris.parquet", event=EVENT)
    stratus.upload_parquet_to_blob(
        out, silver, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    total_t = float(out["debris_tonnes"].sum())
    print(
        f"silver <- {silver} ({len(out):,} damaged buildings; {total_t:,.0f} t debris)",
        flush=True,
    )

    ledger.record(
        SOURCE,
        "silver",
        "UNEP/OCHA JEU building debris (GBA footprints) normalized to silver",
        silver,
        f"{len(out):,} damaged buildings; {total_t:,.0f} t; detected-only "
        f"(no analysed AOI); mass metric (tonnes), not a grade; EPSG:4326",
    )


if __name__ == "__main__":
    main()
