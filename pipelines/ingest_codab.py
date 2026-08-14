"""One-time loader: OCHA CODAB admin boundaries (adm 0-3) from FieldMaps.

Pulls the canonical edge-matched CODs via ocha-stratus' FieldMaps loader and
writes each level to bronze as EPSG:4326 GeoParquet for DuckDB to query. These
boundaries are the reporting/aggregation layer for the harmonization model
(see docs/decisions/0001).

Run: uv run --group etl python pipelines/ingest_codab.py --iso3 COL --adm0 CO
"""

from __future__ import annotations

import argparse

import ocha_stratus as stratus
from ocha_stratus.datasources.codab import load_codab_from_fieldmaps

from gie import ledger
from gie.config import load_settings

STAGE = "dev"
LEVELS = (0, 1, 2, 3)


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest OCHA CODAB admin boundaries (shared reference tree)")
    ap.add_argument("--iso3", required=True, help="country ISO3, e.g. VEN, COL")
    ap.add_argument("--adm0", required=True, help="adm0 partition code, e.g. VE, CO")
    args = ap.parse_args()
    iso3, adm0 = args.iso3.upper(), args.adm0.upper()

    settings = load_settings(STAGE)
    counts = {}
    for level in LEVELS:
        gdf = load_codab_from_fieldmaps(iso3, admin_level=level)
        if gdf is None or len(gdf) == 0:
            print(f"adm{level}: no data returned, skipping")
            continue
        gdf = gdf.to_crs(4326)
        # event=None: CODAB is shared, country-keyed REFERENCE data outside the
        # event tree — reusable across events (spec §3).
        path = settings.blob_path(
            "bronze", "source=codab", f"adm0={adm0}", f"adm{level}.parquet", event=None
        )
        stratus.upload_parquet_to_blob(
            gdf, path, stage=STAGE, container_name=settings.container, compression="zstd"
        )
        counts[f"adm{level}"] = len(gdf)
        print(f"adm{level} <- {path}  ({len(gdf):,} features)")

    ledger.record(
        source="codab",
        layer="bronze",
        dataset=f"OCHA CODAB admin boundaries — {iso3} (FieldMaps)",
        path=settings.blob_path("bronze", "source=codab", f"adm0={adm0}", event=None),
        detail="; ".join(f"{k}={v}" for k, v in counts.items()) + "; EPSG:4326",
    )


if __name__ == "__main__":
    main()
