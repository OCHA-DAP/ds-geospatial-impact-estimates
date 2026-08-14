"""One-time loader: OCHA CODAB admin boundaries (VEN, adm 0-3) from FieldMaps.

Pulls the canonical edge-matched CODs via ocha-stratus' FieldMaps loader and
writes each level to bronze as EPSG:4326 GeoParquet for DuckDB to query. These
boundaries are the reporting/aggregation layer for the harmonization model
(see docs/decisions/0001).

Run: uv run --group etl python pipelines/ingest_codab.py
"""

from __future__ import annotations

import ocha_stratus as stratus
from ocha_stratus.datasources.codab import load_codab_from_fieldmaps

from gie import ledger
from gie.config import load_settings

ISO3 = "VEN"
ADM0 = "VE"
STAGE = "dev"
LEVELS = (0, 1, 2, 3)


def main() -> None:
    settings = load_settings(STAGE)
    counts = {}
    for level in LEVELS:
        gdf = load_codab_from_fieldmaps(ISO3, admin_level=level)
        if gdf is None or len(gdf) == 0:
            print(f"adm{level}: no data returned, skipping")
            continue
        gdf = gdf.to_crs(4326)
        # event=None: CODAB is shared, country-keyed REFERENCE data outside the
        # event tree — reusable across events (spec §3).
        path = settings.blob_path(
            "bronze", "source=codab", f"adm0={ADM0}", f"adm{level}.parquet", event=None
        )
        stratus.upload_parquet_to_blob(
            gdf, path, stage=STAGE, container_name=settings.container, compression="zstd"
        )
        counts[f"adm{level}"] = len(gdf)
        print(f"adm{level} <- {path}  ({len(gdf):,} features)")

    ledger.record(
        source="codab",
        layer="bronze",
        dataset=f"OCHA CODAB admin boundaries — {ISO3} (FieldMaps)",
        path=settings.blob_path("bronze", "source=codab", f"adm0={ADM0}", event=None),
        detail="; ".join(f"{k}={v}" for k, v in counts.items()) + "; EPSG:4326",
    )


if __name__ == "__main__":
    main()
