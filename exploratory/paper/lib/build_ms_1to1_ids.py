"""Freeze the Microsoft -> Overture 1:1 mapping (ADR-0030).

For every damaged, non-superseded Microsoft footprint in the delivery, pick the single Overture
base building with the largest overlap area. Ties (equal area) break on centroid distance, then
Overture id. Footprints touching no base building are orphans: they keep no base building and are
listed in ms_1to1_orphans.csv so the count is auditable. Output: ms_1to1_ids.csv (one Overture id
per row; several MS polygons may share one id).

Run: uv run --group etl python exploratory/paper/artefacts/lib/build_ms_1to1_ids.py
"""
from __future__ import annotations
import glob, os, sys, warnings
warnings.filterwarnings("ignore")
import geopandas as gpd, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gie_paper as gp  # noqa: E402


def main():
    ms = gp.to_metric(gp.microsoft()).reset_index(drop=True).reset_index(names="mid")
    ms["ms_area"] = ms.geometry.area
    print(f"Microsoft damaged, non-superseded footprints: {len(ms):,}")
    parts = sorted(glob.glob(os.path.join(gp.BASE_CACHE, "region=*", "*.parquet")))
    if not parts:
        raise FileNotFoundError(f"Overture base cache missing at {gp.BASE_CACHE}")
    win = gpd.GeoSeries([ms.union_all().envelope], crs=gp.METRIC_CRS).to_crs(4326).iloc[0]
    frames = []
    for p in parts:
        g = gpd.read_parquet(p, columns=["id", "geometry"])
        g = g.set_crs(4326) if g.crs is None else g.to_crs(4326)
        g = g[g.geometry.intersects(win)]
        if len(g):
            frames.append(g)
    base = gp.to_metric(gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326).drop_duplicates("id"))
    print(f"Overture base buildings in the Microsoft envelope: {len(base):,}")

    inter = gpd.overlay(ms[["mid", "ms_area", "geometry"]], base[["id", "geometry"]], how="intersection", keep_geom_type=False)
    inter["ov_area"] = inter.geometry.area
    inter = inter[inter.ov_area > 0]
    # tie-break: centroid distance, then id
    mc = ms.set_index("mid").geometry.centroid
    bc = base.set_index("id").geometry.centroid
    inter["cdist"] = [mc.loc[m].distance(bc.loc[i]) for m, i in zip(inter.mid, inter.id)]
    inter = inter.sort_values(["mid", "ov_area", "cdist", "id"], ascending=[True, False, True, True])
    best = inter.groupby("mid").head(1)
    second = inter.groupby("mid").nth(1)
    ties = int((second.set_index("mid").ov_area.reindex(best.mid.values).values == best.ov_area.values).sum()) if len(second) else 0
    orphans = ms[~ms.mid.isin(best.mid)]
    ids = pd.DataFrame({"id": sorted(set(best["id"]))})
    ids.to_csv(os.path.join(HERE, "ms_1to1_ids.csv"), index=False)
    orphans[["mid", "ms_area"]].assign(centroid_lon=orphans.geometry.centroid.to_crs(4326).x.values,
                                       centroid_lat=orphans.geometry.centroid.to_crs(4326).y.values) \
        .to_csv(os.path.join(HERE, "ms_1to1_orphans.csv"), index=False)
    print(f"mapped: {len(best):,} MS footprints -> {len(ids):,} Overture buildings "
          f"(sharing a building: {len(best)-len(ids):,}; exact-area ties broken by distance: {ties}); "
          f"orphans: {len(orphans):,} ({len(orphans)/len(ms)*100:.2f}%)")
    print(f"median share of MS footprint area covered by its chosen building: {(best.ov_area/best.ms_area).median():.2f}")
    print("wrote lib/ms_1to1_ids.csv, lib/ms_1to1_orphans.csv")


if __name__ == "__main__":
    main()
