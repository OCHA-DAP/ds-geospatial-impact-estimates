"""Microsoft -> Overture by MAX-OVERLAP (1:1), with tie and orphan diagnostics, core region."""
from __future__ import annotations
import os, sys, warnings
warnings.filterwarnings("ignore")
import geopandas as gpd, pandas as pd, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
import gie_paper as gp  # noqa: E402
from native_vs_centroid_core import core_region, match_rate  # noqa: E402

uh_all = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
core = core_region(uh_all)
pts = gp.to_metric(gp.cems_points()); cems = pts[pts.damage_class.isin([2, 3])]; cems = cems[cems.within(core)]
b = gpd.GeoSeries([core], crs=gp.METRIC_CRS).to_crs(4326).total_bounds
ov = gp.to_metric(gp.overture_window(*b)); ov = ov[ov.geometry.representative_point().within(core)][["id", "geometry"]]
ms = gp.to_metric(gp.microsoft()); ms = ms[ms.geometry.representative_point().within(core)].reset_index(drop=True).reset_index(names="mid")
ms["ms_area"] = ms.geometry.area

# all intersecting pairs with overlap area
inter = gpd.overlay(ms[["mid", "ms_area", "geometry"]], ov, how="intersection", keep_geom_type=False)
inter["ov_area"] = inter.geometry.area
inter["share"] = inter.ov_area / inter.ms_area
n_pairs = len(inter); n_ms_with_hit = inter.mid.nunique()
orphans = len(ms) - n_ms_with_hit
# best match per MS polygon
inter = inter.sort_values(["mid", "ov_area"], ascending=[True, False])
best = inter.groupby("mid").head(2)
top = best.groupby("mid").nth(0); second = best.groupby("mid").nth(1).set_index("mid")
top = top.set_index("mid")
ratio = (second.ov_area.reindex(top.index) / top.ov_area).fillna(0)
ties_exact = int((ratio == 1.0).sum()); near_ties = int(((ratio > 0.9) & (ratio < 1.0)).sum())
print(f"MS damaged polygons in core: {len(ms):,}")
print(f"  intersecting pairs: {n_pairs:,}  (mean {n_pairs/n_ms_with_hit:.2f} Overture buildings touched per MS polygon)")
print(f"  orphans (touch no Overture footprint): {orphans}  = {orphans/len(ms)*100:.2f}%")
print(f"  exact ties for max overlap: {ties_exact} | near-ties (2nd within 10% of 1st): {near_ties}")
print(f"  max-overlap share of MS polygon area covered by its chosen footprint: median {top.share.median():.2f}, 10th pct {top.share.quantile(.1):.2f}")
ids_max = set(top["id"]); print(f"  1:1 max-overlap flagged Overture buildings: {len(ids_max):,} (MS polygons sharing a footprint: {len(top)-len(ids_max):,})")

# compare with point-on-surface 1:1
pos = gpd.sjoin(gpd.GeoDataFrame(geometry=ms.geometry.representative_point(), crs=ms.crs).assign(mid=ms.mid), ov, predicate="within", how="inner")
ids_pos = set(pos["id"]); agree = len(ids_max & ids_pos)
print(f"  point-on-surface flagged: {len(ids_pos):,}; overlap with max-overlap set: {agree:,} (max-only {len(ids_max-ids_pos)}, pos-only {len(ids_pos-ids_max)})")

def score(sub, r=10):
    tp_r, n = match_rate(cems, sub, r); tp_p, nf = match_rate(sub, cems, r); R, P = tp_r/n, tp_p/nf
    return P, R, 2*P*R/(P+R)
flag_max = ov[ov["id"].isin(ids_max)]
P, R, F = score(flag_max); print(f"  MS max-overlap 1:1, polygon frame r=10: P={P:.3f} R={R:.3f} F1={F:.3f}")
# orphans kept raw: add the untouched MS polygons themselves to the flag set
orph = ms[~ms.mid.isin(inter.mid)][["geometry"]]
both = pd.concat([flag_max[["geometry"]], orph], ignore_index=True)
P, R, F = score(gpd.GeoDataFrame(both, crs=ov.crs)); print(f"  ...plus {len(orph)} orphans kept as raw MS polygons: P={P:.3f} R={R:.3f} F1={F:.3f}")
