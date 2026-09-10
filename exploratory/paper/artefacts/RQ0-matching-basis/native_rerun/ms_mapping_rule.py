"""Effect of the Microsoft->Overture mapping rule (intersects vs 1:1 point-on-surface), core region.

Venezuela gold maps Microsoft by ST_Intersects (one-to-many); the Colombia pipeline maps by
point-on-surface containment (1:1, ADR-0015). Re-map here with the 1:1 rule, re-score Microsoft
and the k-of-6 rules (polygon-distance frame), and compare with the gold-based numbers.
Run: uv run --group etl python exploratory/paper/artefacts/RQ0-matching-basis/native_rerun/ms_mapping_rule.py
"""
from __future__ import annotations
import os, sys, warnings
warnings.filterwarnings("ignore")
import geopandas as gpd, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
import gie_paper as gp  # noqa: E402
from native_vs_centroid_core import core_region, match_rate  # noqa: E402
FLAGS = {"Microsoft": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg", "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}

uh_all = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
core = core_region(uh_all)
pts = gp.to_metric(gp.cems_points()); cems = pts[pts.damage_class.isin([2, 3])]; cems = cems[cems.within(core)]
b = gpd.GeoSeries([core], crs=gp.METRIC_CRS).to_crs(4326).total_bounds
ov = gp.to_metric(gp.overture_window(*b)); ov = ov[ov.geometry.representative_point().within(core)]
flags = gp.building_flags(columns=list(FLAGS.values()))
bld = ov.merge(flags, on="id", how="inner")
for c in FLAGS.values(): bld[c] = bld[c].fillna(False).astype(bool).astype(int)

# 1:1 re-map of Microsoft: Overture footprint containing the MS polygon's point-on-surface
ms = gp.to_metric(gp.microsoft()); ms = ms[ms.geometry.representative_point().within(core)]
ms_pts = gpd.GeoDataFrame(geometry=ms.geometry.representative_point(), crs=ms.crs)
hit = gpd.sjoin(ms_pts, bld[["id", "geometry"]], predicate="within", how="inner")
ids_1to1 = set(hit["id"])
bld["ms_1to1"] = bld["id"].isin(ids_1to1).astype(int)
print(f"MS delivered damaged polygons in core: {len(ms):,}")
print(f"  gold (ST_Intersects) flagged Overture buildings: {int(bld.ms_dmg.sum()):,}")
print(f"  1:1 point-on-surface flagged Overture buildings: {int(bld.ms_1to1.sum()):,}  (polygons landing on no footprint: {len(ms)-len(hit):,}; polygons sharing a footprint: {len(hit)-len(ids_1to1):,})")
print(f"  buildings flagged by gold but NOT by 1:1 (neighbour bleed): {int(((bld.ms_dmg==1)&(bld.ms_1to1==0)).sum()):,}")

def score(sub, r=10):
    tp_r, n = match_rate(cems, sub, r); tp_p, nf = match_rate(sub, cems, r)
    R, P = tp_r/n, tp_p/nf; return P, R, 2*P*R/(P+R)
for lab, col in (("MS gold (intersects)", "ms_dmg"), ("MS 1:1 remap", "ms_1to1")):
    P, R, F = score(bld[bld[col] == 1]); print(f"  {lab:22} polygon-frame r=10: P={P:.3f} R={R:.3f} F1={F:.3f}")

others = [c for c in FLAGS.values() if c != "ms_dmg"]
bld["k_gold"] = bld[list(FLAGS.values())].sum(axis=1)
bld["k_1to1"] = bld[others].sum(axis=1) + bld["ms_1to1"]
print("\nk-of-6 rules, polygon frame r=10 (gold MS mapping -> 1:1 MS mapping):")
for k in range(1, 7):
    g = bld[bld.k_gold >= k]; o = bld[bld.k_1to1 >= k]
    Pg, Rg, Fg = score(g); Po, Ro, Fo = score(o)
    print(f"  {k}-of-6: n {len(g):6,} -> {len(o):6,} | P {Pg:.3f} -> {Po:.3f} | R {Rg:.3f} -> {Ro:.3f} | F1 {Fg:.3f} -> {Fo:.3f}")
