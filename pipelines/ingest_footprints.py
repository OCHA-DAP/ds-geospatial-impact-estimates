"""One-time loader: Microsoft predicted building-damage footprints, Catia La Mar.

Source: HDX "Venezuela Earthquakes: Building Damage Assessment in Catia La Mar"
(CC-BY, attribution required). Stores the raw GeoPackage in bronze (audit
trail) and writes a standardized EPSG:4326 GeoParquet to silver for DuckDB to
query. Uses ocha-stratus for the one-time write only (see docs/decisions/0003).

Run: uv run --group etl python pipelines/ingest_footprints.py
"""

from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path

import geopandas as gpd
import ocha_stratus as stratus

from gie import ledger
from gie.config import load_settings

HDX_GPKG_URL = (
    "https://data.humdata.org/dataset/029efb88-3a8a-40d9-8aea-65477e6eb744/"
    "resource/684fdeab-e4ac-4029-9ec9-891676b2ebfc/download/"
    "predicted_damage_catia_la_mar_footprints.gpkg"
)
SOURCE = "microsoft"
ADM0 = "VE"
STAGE = "dev"


def main() -> None:
    settings = load_settings(STAGE)
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "footprints.gpkg"
        print(f"Downloading {HDX_GPKG_URL.rsplit('/', 1)[-1]} ...")
        urllib.request.urlretrieve(HDX_GPKG_URL, local)  # noqa: S310 (trusted HDX URL)

        # bronze: raw file, exactly as received (audit trail, never mutated).
        bronze = settings.blob_path(
            "bronze",
            f"source={SOURCE}",
            f"adm0={ADM0}",
            "predicted_damage_catia_la_mar_footprints.gpkg",
        )
        stratus.upload_blob_data(
            local.read_bytes(), bronze, stage=STAGE, container_name=settings.container
        )
        print(f"bronze <- {bronze}")

        # silver: standardized GeoParquet (EPSG:4326), zstd-compressed.
        gdf = gpd.read_file(local).to_crs(4326)
        silver = settings.blob_path(
            "silver", f"source={SOURCE}", f"adm0={ADM0}", "footprints.parquet"
        )
        stratus.upload_parquet_to_blob(
            gdf, silver, stage=STAGE, container_name=settings.container, compression="zstd"
        )
        print(f"silver <- {silver}  ({len(gdf):,} footprints, EPSG:4326)")

        ledger.record(
            SOURCE, "bronze", "Building footprints — Catia La Mar (raw GPKG)",
            bronze, "GeoPackage as received from HDX (CC-BY)",
        )
        ledger.record(
            SOURCE, "silver", "Building footprints — Catia La Mar", silver,
            f"{len(gdf):,} footprints; binary damaged + damage_pct; EPSG:4326",
        )


if __name__ == "__main__":
    main()
