"""Silver: harmonise the Microsoft MERGED dataset onto the common schema.

Reads the merged building predictions + unioned valid-area mask from bronze
(.../merged/), reprojects to EPSG:4326, and writes the Microsoft silver
footprints.parquet + analysed_extent.parquet — REPLACING the per-AOI silver.

The merge is already deduplicated across AOIs and reconciles multi-observation
damage, so there is no per-AOI supersession here: the single unioned extent is
superseded=False and every building is kept. Schema matches the prior per-AOI
silver (damaged/damage_pct_10m/aoi/superseded/geometry/adm0/source) so it is a
drop-in for harmonize_common + serving; num_observations/uncertainty are carried
along for future use.

Run: uv run --group etl python pipelines/harmonize_microsoft.py
"""

from __future__ import annotations

import os
import tempfile

import geopandas as gpd
import ocha_stratus as stratus

from gie import blob, ledger
from gie.config import load_settings

SOURCE = "microsoft"
ADM0 = "VE"
STAGE = "dev"
FOOTPRINTS_SRC = "ALL_AOIS_building_predictions_deduplicated.gpkg"
MASK_SRC = "valid_area_mask_union.geojson"


def _read_bronze(settings, name: str) -> gpd.GeoDataFrame:
    bp = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", "merged", name)
    data = stratus.load_blob_data(bp, stage=STAGE, container_name=settings.container)
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(name)[1], delete=False) as tf:
        tf.write(data)
        tmp = tf.name
    gdf = gpd.read_file(tmp)
    os.unlink(tmp)
    return gdf


def main() -> None:
    settings = load_settings(STAGE)

    # footprints: reproject to 4326, keep the common-schema columns
    fp = _read_bronze(settings, FOOTPRINTS_SRC).to_crs(4326)
    foot = fp[["damaged", "damage_pct_10m", "num_observations", "uncertainty", "geometry"]].copy()
    foot["damaged"] = foot["damaged"].astype("int64")
    foot["aoi"] = "merged"
    foot["superseded"] = False
    foot["adm0"] = ADM0
    foot["source"] = SOURCE
    fblob = settings.blob_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "footprints.parquet")
    blob.upload_parquet_staged(foot, fblob, settings)
    n_dmg = int(foot["damaged"].sum())
    print(f"silver <- {fblob} ({len(foot):,} buildings, {n_dmg:,} damaged)", flush=True)

    # analysed extent: the single unioned valid-area mask
    mask = _read_bronze(settings, MASK_SRC).to_crs(4326)
    ext = mask[["geometry"]].copy()
    ext["aoi"] = "All AOIs (merged)"
    ext["superseded"] = False
    ext["adm0"] = ADM0
    ext["source"] = SOURCE
    eblob = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    blob.upload_parquet_staged(ext, eblob, settings)
    print(f"silver <- {eblob} ({len(ext)} merged extent polygon)", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "Microsoft merged dataset harmonised to silver (replaces per-AOI)",
        fblob,
        f"{len(foot):,} deduplicated buildings ({n_dmg:,} damaged), EPSG:4326; single unioned "
        "analysed extent (superseded=False); supersedes the per-AOI silver footprints + masks.",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
