"""Freeze the paper's own-footprint -> Overture base mapping for every product that delivered its
own building geometry (ADR-0030, rule set agreed 2026-09-14). One rule for all of them:

  1. each delivered damaged footprint maps to the ONE base building with the highest IoU among
     the base buildings it overlaps;
  2. a footprint overlapping no base building maps to the nearest base building whose footprint
     lies within SNAP_M metres (the tolerance gold uses for point deliveries);
  3. beyond that it is an orphan: counted, listed, mapped to nothing;
  4. one assignment per delivered footprint, never one-to-many; several footprints may share a
     base building (the collapse is counted).

Outputs, beside this file, one set per product:
  <key>_1to1_ids.csv       the base ids flagged (one row per id)
  <key>_1to1_orphans.csv   delivered footprints mapped to nothing
  footprint_map_manifest.csv   per product: delivered, overlapping, snapped, orphans, base ids, collapse

Run: uv run --group etl python exploratory/paper/artefacts/lib/build_footprint_maps.py
"""
from __future__ import annotations

import glob
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import geopandas as gpd
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gie_paper as gp  # noqa: E402

SNAP_M = 20

PRODUCTS = {
    # key: (loader of the damaged, non-superseded delivered footprints in METRIC_CRS)
    "ms": lambda: gp.to_metric(gp.microsoft()),
    "unep": lambda: gp.to_metric(gp._read_pq("silver", "source=unep_debris", "adm0=VE", "debris.parquet")),
    "uh": lambda: (lambda g: g[g.cls.isin([2, 3])])(gp.to_metric(gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet"))),
}


def base_in(src: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    parts = sorted(glob.glob(os.path.join(gp.BASE_CACHE, "region=*", "*.parquet")))
    if not parts:
        raise FileNotFoundError(f"Overture base cache missing at {gp.BASE_CACHE}")
    win = gpd.GeoSeries([src.union_all().envelope.buffer(SNAP_M * 2)], crs=gp.METRIC_CRS).to_crs(4326).iloc[0]
    frames = []
    for p in parts:
        g = gpd.read_parquet(p, columns=["id", "geometry"])
        g = g.set_crs(4326) if g.crs is None else g.to_crs(4326)
        g = g[g.geometry.intersects(win)]
        if len(g):
            frames.append(g)
    b = gp.to_metric(gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326).drop_duplicates("id"))
    b["b_area"] = b.geometry.area
    return b


def map_product(key: str) -> dict:
    src = PRODUCTS[key]().reset_index(drop=True).reset_index(names="sid")
    src["s_area"] = src.geometry.area
    base = base_in(src)
    inter = gpd.overlay(src[["sid", "s_area", "geometry"]], base[["id", "b_area", "geometry"]], how="intersection", keep_geom_type=False)
    inter["ov"] = inter.geometry.area
    inter = inter[inter.ov > 0]
    inter["iou"] = inter.ov / (inter.s_area + inter.b_area - inter.ov)
    best = inter.sort_values(["sid", "iou", "id"], ascending=[True, False, True]).groupby("sid").head(1)[["sid", "id", "iou"]]
    best["how"] = "iou"
    # rule 2: no overlap -> nearest base building within SNAP_M (boundary distance)
    rest = src[~src.sid.isin(best.sid)]
    if len(rest):
        j = gpd.sjoin_nearest(rest[["sid", "geometry"]], base[["id", "geometry"]], max_distance=SNAP_M, how="left", distance_col="d")
        j = j[~j.index.duplicated()]
        snapped = j[j.id.notna()][["sid", "id"]].assign(iou=0.0, how="snap")
        best = pd.concat([best, snapped], ignore_index=True)
    orphans = src[~src.sid.isin(best.sid)]
    ids = pd.DataFrame({"id": sorted(set(best.id))})
    ids.to_csv(os.path.join(HERE, f"{key}_1to1_ids.csv"), index=False)
    orphans[["sid", "s_area"]].assign(centroid_lon=orphans.geometry.centroid.to_crs(4326).x.values,
                                      centroid_lat=orphans.geometry.centroid.to_crs(4326).y.values) \
        .to_csv(os.path.join(HERE, f"{key}_1to1_orphans.csv"), index=False)
    row = dict(product=key, delivered=len(src), mapped_by_iou=int((best.how == "iou").sum()), mapped_by_snap=int((best.how == "snap").sum()),
               orphans=len(orphans), base_ids=len(ids), collapsed=int(len(best) - len(ids)),
               median_iou=round(float(best.loc[best.how == "iou", "iou"].median()), 3))
    print(row, flush=True)
    return row


def main():
    rows = [map_product(k) for k in PRODUCTS]
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "footprint_map_manifest.csv"), index=False)
    print("wrote lib/<key>_1to1_ids.csv, lib/<key>_1to1_orphans.csv, lib/footprint_map_manifest.csv")


if __name__ == "__main__":
    main()
