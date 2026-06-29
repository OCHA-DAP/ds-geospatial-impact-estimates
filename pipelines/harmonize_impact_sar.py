"""Project the IMPACT Sentinel-1 SAR damage proxy onto the Overture base -> silver.

Reads the bronze proxy raster (masked z-score > 0.7) and samples it at each
Overture building centroid inside the raster's extent, standardising the two
thresholds to the Copernicus damage_class model (ADR-0008):
    0.7 <= z < 1.0  -> Possibly damaged (class 1)
    z >= 1.0        -> Damaged          (class 2)
The grade encodes SAR *confidence*, not severity, and the whole layer is a
hotspot/gap SCREEN, not confirmed damage (side-look SAR -> debris/moisture/veg).

Sampling (not vectorising) keeps this tractable at ~10 m / 116M pixels. Output:
  * building_damage.parquet — one row per SAR-DAMAGED building (id, z, grade).
  * analysed_extent.parquet — the raster's bounds rectangle = the SAR footprint
    (the file is masked, so per ADR-0008 the raster extent IS the footprint).

TEMPORARY (ADR-0008): downstream we only put the *damaged* buildings on the
per-building layer; the ~3.7M analysed buildings are not materialised there until
PMTiles/vector tiling lands.

Run: uv run --group etl python pipelines/harmonize_impact_sar.py
"""

from __future__ import annotations

import os
import tempfile

import geopandas as gpd
import numpy as np
import ocha_stratus as stratus
import pandas as pd
import rasterio
from rasterio.transform import rowcol
from shapely.geometry import box

from gie import db, ledger
from gie.config import load_settings

SOURCE = "impact_initiatives"
ADM0 = "VE"
STAGE = "dev"
RASTER = "IMPACT_VEN_20260625_Sentinel1_damage_proxy_gt0.70.tif"
DAMAGE_THRESHOLD = 0.7  # provided masked at this; class 2 at >= 1.0 (ADR-0008)


def main() -> None:
    settings = load_settings(STAGE)
    con = db.connect()

    # pull the bronze raster to a temp file and read it fully (random-access sampling)
    bpath = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", RASTER)
    raw = stratus.load_blob_data(bpath, stage=STAGE, container_name=settings.container)
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tf:
        tf.write(raw)
        tmp = tf.name
    del raw
    with rasterio.open(tmp) as src:
        arr = src.read(1)
        transform, nodata, (h, w) = src.transform, src.nodata, src.shape
        b = src.bounds
    os.unlink(tmp)

    # Overture centroids inside the raster extent (deduped base)
    base = settings.az_path("silver", "source=overture", f"adm0={ADM0}", "region=*", "*.parquet")
    df = con.execute(
        f"""
        SELECT id, ST_X(c) AS lon, ST_Y(c) AS lat FROM (
            SELECT id, ST_Centroid(geometry) AS c
            FROM read_parquet('{base}', hive_partitioning=true)
            QUALIFY row_number() OVER (PARTITION BY id) = 1
        )
        WHERE lon BETWEEN {b.left} AND {b.right} AND lat BETWEEN {b.bottom} AND {b.top}
        """
    ).df()

    rows, cols = rowcol(transform, df["lon"].to_numpy(), df["lat"].to_numpy())
    rows, cols = np.asarray(rows), np.asarray(cols)
    inb = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
    z = np.full(len(df), np.nan, dtype="float32")
    z[inb] = arr[rows[inb], cols[inb]]
    dmg = np.isfinite(z) & (z != nodata) & (z >= DAMAGE_THRESHOLD)

    out = pd.DataFrame(
        {
            "id": df["id"].to_numpy()[dmg],
            "sar_z": z[dmg],
            "damage_class": np.where(z[dmg] >= 1.0, 2, 1).astype("int32"),
        }
    )
    out["ems_grade"] = np.where(out["damage_class"] == 2, "Damaged", "Possibly damaged")
    sp = settings.blob_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "building_damage.parquet")
    stratus.upload_parquet_to_blob(
        out, sp, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    n2 = int((out["damage_class"] == 2).sum())
    print(
        f"silver <- {sp} ({len(out):,} SAR-damaged buildings of {len(df):,} in extent; "
        f"class2 (z>=1) = {n2:,})",
        flush=True,
    )

    # footprint = raster bounds rectangle (the file is masked; bounds = footprint)
    fp = gpd.GeoDataFrame(
        {"source": [SOURCE]},
        geometry=[box(b.left, b.bottom, b.right, b.top)],
        crs="EPSG:4326",
    )
    fpath = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    stratus.upload_parquet_to_blob(
        fp, fpath, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {fpath} (footprint = raster bounds)", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "IMPACT SAR proxy projected onto Overture buildings (z>0.7 -> CEMS grades)",
        sp,
        f"{len(out):,} damaged buildings (class1 0.7-1.0, class2 >=1.0); "
        "footprint = raster bounds; DAMAGED-ONLY stopgap per ADR-0008",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
