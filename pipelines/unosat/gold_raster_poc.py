"""Gold v3 proof of concept: rasterise label sets directly, no dissolve (ADR-0037).

Same grouping as gold (area, acquisition interval), same class rules, but each
label set is BURNED onto the 30 arcsec fusion grid instead of unioned in vector
space. Burning is a logical OR, footprint-minus-cloud is AND NOT, and a
scanline rasteriser does not care whether a polygon is valid — so the three
expensive GEOS steps (repair, union, difference) disappear.

Writes one 4-band uint8 GeoTIFF per label set under
  {work_dir}/gold_raster_poc/code={code}/{area}_{start}_{end}.tif
    band 1 water  (flood | water_pre | water) present at acquisition
    band 2 flood  (flood kinds only; 0 where the source never separated it)
    band 3 possible
    band 4 valid  (footprint minus not_analysed; 0 = unobserved, not dry)
and prints per-label-set timings. Reads the local silver mirror only.

Run:  uv run --group etl --group api python pipelines/unosat/gold_raster_poc.py --codes
FL20250812CPV
"""

from __future__ import annotations

import argparse
import glob
import time
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from rasterio.features import rasterize

from gie.unosat import common, gold, silver

RES = 1.0 / 120.0  # 30 arcsec, EPSG:4326 — the fusion grid (ds-flood-gfm spec)


def grid_for(
    bounds: tuple[float, float, float, float], res: float = RES
) -> tuple[Affine, int, int]:
    """A window of the global 1/120° grid covering ``bounds``, snapped so its
    cells are the global grid's cells (integer row/col identity is the fusion
    contract), not an arbitrary local raster."""
    minx, miny, maxx, maxy = bounds
    c0, c1 = int(np.floor((minx + 180) / res)), int(np.ceil((maxx + 180) / res))
    r0, r1 = int(np.floor((90 - maxy) / res)), int(np.ceil((90 - miny) / res))
    return Affine(res, 0, -180 + c0 * res, 0, -res, 90 - r0 * res), r1 - r0, c1 - c0


def burn(geoms, transform: Affine, h: int, w: int) -> np.ndarray:
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros((h, w), dtype=np.uint8)
    return rasterize(
        ((g, 1) for g in geoms),
        out_shape=(h, w),
        transform=transform,
        fill=0,
        all_touched=False,
        dtype=np.uint8,
    )


def rasterise_label_set(
    group: pd.DataFrame, footprint, masked, transform, h, w
) -> dict[str, np.ndarray]:
    contributing = group[~group["layer_kind"].isin(gold.EXCLUDED_KINDS)]
    out = {
        "water": burn(
            contributing[contributing["layer_kind"].isin(gold.WATER_KINDS)].geometry,
            transform,
            h,
            w,
        ),
        "flood": burn(
            contributing[contributing["layer_kind"].isin(gold.FLOOD_KINDS)].geometry,
            transform,
            h,
            w,
        ),
        "possible": burn(
            contributing[contributing["layer_kind"].isin(gold.POSSIBLE_KINDS)].geometry,
            transform,
            h,
            w,
        ),
    }
    valid = (
        burn(footprint.geometry, transform, h, w) if len(footprint) else np.zeros((h, w), np.uint8)
    )
    if len(masked):
        valid &= ~burn(masked.geometry, transform, h, w) & 1
    out["valid"] = valid
    return out


def build_code_raster(code: str, observed, coverage, out_dir: Path) -> list[dict]:
    """The gold grouping, then a burn per label set. Returns per-set timings."""
    obs = gold._prepare(observed, code=code, table="observed_event", method="none")
    cov = gold._prepare(coverage, code=code, table="coverage", method="none")
    rows = []
    for (aoi, start, end), group in obs.groupby(
        ["area_label", "acq_start", "acq_end"], dropna=False, sort=True
    ):
        t0 = time.perf_counter()
        # coverage matching as gold does it: same source zip(s) and same area, exact interval preferred
        ids = set().union(*(set(t) for t in group["target_ids"]))
        shares_source = [bool(set(t) & ids) for t in cov["target_ids"]]
        same = cov[pd.Series(shares_source, index=cov.index) & (cov["area_label"] == aoi)]
        exact = same[(same["acq_start"] == start) & (same["acq_end"] == end)]
        pool = exact if len(exact[exact["role"] == "footprint"]) else same
        footprint = pool[pool["role"] == "footprint"]
        masked = pool[pool["role"] == "not_analysed"]
        ext = pd.concat([group.geometry, footprint.geometry]) if len(footprint) else group.geometry
        transform, h, w = grid_for(tuple(ext.total_bounds))
        bands = rasterise_label_set(group, footprint, masked, transform, h, w)
        name = f"{aoi}_{pd.Timestamp(start):%Y%m%d}_{pd.Timestamp(end):%Y%m%d}.tif"
        out_dir.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            out_dir / name,
            "w",
            driver="GTiff",
            height=h,
            width=w,
            count=4,
            dtype="uint8",
            crs="EPSG:4326",
            transform=transform,
            compress="deflate",
            tiled=True,
        ) as dst:
            for i, k in enumerate(("water", "flood", "possible", "valid"), 1):
                dst.write(bands[k], i)
                dst.set_band_description(i, k)
        dt = time.perf_counter() - t0
        rows.append(
            {
                "code": code,
                "area": aoi,
                "start": start,
                "end": end,
                "polygons": len(group),
                "vertices": int(
                    sum(
                        len(g.exterior.coords)
                        if g.geom_type == "Polygon"
                        else sum(len(p.exterior.coords) for p in g.geoms)
                        for g in group.geometry
                        if g is not None
                    )
                ),
                "cells": h * w,
                "water_cells": int(bands["water"].sum()),
                "valid_cells": int(bands["valid"].sum()),
                "seconds": round(dt, 3),
                "file": str(out_dir / name),
            }
        )
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument(
        "--codes",
        required=True,
        help="comma-separated event codes (local silver mirror must hold them)",
    )
    args = ap.parse_args(argv)
    mirror = silver.local_mirror(args.work_dir)
    for code in [c.strip() for c in args.codes.split(",") if c.strip()]:
        t0 = time.perf_counter()

        def part(table: str, code: str = code) -> pd.DataFrame:
            files = sorted(glob.glob(str(mirror / table / f"code={code}" / "layer=*.parquet")))
            return pd.concat([silver.read_layer_file(Path(f)) for f in files], ignore_index=True)

        observed, coverage = part("observed_event"), part("coverage")
        rows = build_code_raster(
            code, observed, coverage, args.work_dir / "gold_raster_poc" / f"code={code}"
        )
        total = time.perf_counter() - t0
        print(f"{code}: {len(rows)} label sets from {len(observed)} polygons in {total:.2f}s total")
        for r in rows:
            print(
                f"   {r['area']:<22} {r['polygons']:>7} polys {r['vertices']:>10,} verts  "
                f"{r['cells']:>8,} cells  water={r['water_cells']:>7,}  valid={r['valid_cells']:>8,}  {r['seconds']:6.2f}s"
            )


if __name__ == "__main__":
    main()
