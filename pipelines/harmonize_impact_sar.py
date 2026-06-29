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
  * analysed_extent.parquet — the raster bounds clipped to the validated S1 swath
    coverage (from IMPACT's acquisition footprints; drops the masked SE edge), the
    true analysed AOI that supersedes the ADR-0008 raster-bounds stopgap.

TEMPORARY (ADR-0008): downstream we only put the *damaged* buildings on the
per-building layer; the ~3.7M analysed buildings are not materialised there until
PMTiles/vector tiling lands.

Run: uv run --group etl python pipelines/harmonize_impact_sar.py
"""

from __future__ import annotations

import io
import os
import tempfile

import geopandas as gpd
import numpy as np
import ocha_stratus as stratus
import pandas as pd
import rasterio
import shapely
from rasterio.transform import rowcol
from shapely.geometry import Polygon, box

from gie import db, ledger
from gie.config import load_settings

SOURCE = "impact_initiatives"
ADM0 = "VE"
STAGE = "dev"
RASTER = "IMPACT_VEN_20260625_Sentinel1_damage_proxy_gt0.70.tif"
DAMAGE_THRESHOLD = 0.7  # provided masked at this; class 2 at >= 1.0 (ADR-0008)
FOOTPRINTS = "acquisition_footprints.parquet"  # bronze: 2 S1D acquisition outlines


def _analysed_extent(settings, b):
    """Validated SAR coverage = raster box clipped to the S1 swath whose edge cuts
    through it.

    IMPACT delivered the two S1D acquisition footprints and noted they masked the
    single-swath southern/SE edge ("footprint-aligned inflation", visual QA). The
    honest analysed area is the raster bounds intersected with that clipping swath
    — keeps the NW corner, drops the SE triangle (~31% of the box). Supersedes the
    raster-bounds stopgap (ADR-0008).
    """
    raw = stratus.load_blob_data(
        settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", FOOTPRINTS),
        stage=STAGE,
        container_name=settings.container,
    )
    swaths = [Polygon(list(g.coords)).buffer(0) for g in gpd.read_parquet(io.BytesIO(raw)).geometry]
    rect = box(b.left, b.bottom, b.right, b.top)
    # the clipping swath is the one whose box-intersection is smallest (its edge
    # cuts through the box); the other swath ~contains the box.
    clips = [c for c in (rect.intersection(s) for s in swaths) if not c.is_empty]
    return min(clips, key=lambda g: g.area)


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

    # Restrict to the validated analysed extent (drop the masked SE single-swath
    # edge), so damaged ⊆ analysed and the inflation artifacts there are excluded.
    extent = _analysed_extent(settings, b)
    dmg &= shapely.contains_xy(extent, df["lon"].to_numpy(), df["lat"].to_numpy())

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

    # analysed extent = raster box clipped to the validated swath (see _analysed_extent)
    fp = gpd.GeoDataFrame({"source": [SOURCE]}, geometry=[extent], crs="EPSG:4326")
    fpath = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    stratus.upload_parquet_to_blob(
        fp, fpath, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {fpath} (footprint = S1 swath-clipped extent)", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "IMPACT SAR proxy projected onto Overture buildings (z>0.7 -> CEMS grades)",
        sp,
        f"{len(out):,} damaged buildings (class1 0.7-1.0, class2 >=1.0); "
        "analysed extent = S1 swath-clipped (true AOI, supersedes ADR-0008 bounds)",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
