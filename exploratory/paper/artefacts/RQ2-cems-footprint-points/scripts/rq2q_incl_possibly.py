"""RQ2q — sensitivity: does including CEMS 'possibly damaged' (class 1) change anything?

The paper's reference is CEMS {Damaged(2), Destroyed(3)}; class 1 is excluded from every
score (#app-matching). An early pre-freeze artefact (rq2_points, 3 products, pre-MONIT2
reference, pre-merged-refresh Microsoft) reported an incl-possibly variant, but its levels
do not carry to the frozen basis. This re-runs the sensitivity on the paper's frozen data:
gold building_flags (OSU v0-pinned), CEMS latest-monitoring points, the RQ5b core region
(construction copied verbatim), centroid matching at r = 10 m (within 0.005 of the native
scorecard, see #tbl-frames). Scores all six products AND the k-of-6 voting rules under both
thresholds, so the check covers the ensemble headline the early artefact never touched.

Run: uv run --group etl --with scipy --with h3 python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2q_incl_possibly.py
"""
from __future__ import annotations
import os, sys

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
R = 10
MEMBERS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
           "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}
THRESHOLDS = {"dmg+destroyed": (2, 3), "incl_possibly": (1, 2, 3)}


def uh_aoi():
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    g = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    cells = {h3.latlng_to_cell(p.y, p.x, 9) for p in g.geometry.representative_point()}
    dil = set()
    for c in cells:
        dil.update(h3.grid_disk(c, 1))
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in dil]
    return gp.dissolve_union(gpd.GeoDataFrame(geometry=[unary_union(polys)], crs=4326))


def main():
    df = gp.building_flags(columns=["lon", "lat", *MEMBERS.values()])
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    votes = df[list(MEMBERS.values())].sum(axis=1)

    region = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    for a in (gp.dissolve_union(gp.microsoft_aoi()), gp.dissolve_union(gp.impact_v2_aoi()),
              gp.dissolve_union(gp.osu_aoi()), uh_aoi(),
              gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                            "analysed_extent.parquet"))):
        region = region.intersection(a)
    in_reg = bld.geometry.within(region)

    cems = gp.to_metric(gp.cems_points())
    rules = [(nm, in_reg & (df[col] == 1)) for nm, col in MEMBERS.items()]
    rules += [(f"{k}-of-6", in_reg & (votes >= k)) for k in range(1, 7)]

    rows = []
    for tname, classes in THRESHOLDS.items():
        cpts = cems[cems.damage_class.isin(classes) & cems.geometry.within(region)]
        ct = cKDTree(np.c_[cpts.geometry.x, cpts.geometry.y])
        print(f"[{tname}] reference points in core: {len(cpts):,}")
        for nm, mask in rules:
            f = bld[mask.values]
            ft = cKDTree(np.c_[f.geometry.x, f.geometry.y])
            prec = (ct.query(np.c_[f.geometry.x, f.geometry.y], k=1)[0] <= R).mean()
            rec = (ft.query(np.c_[cpts.geometry.x, cpts.geometry.y], k=1)[0] <= R).mean()
            f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
            rows.append(dict(threshold=tname, rule=nm, flags=len(f), cems_pts=len(cpts),
                             P=round(prec, 3), R=round(rec, 3), F1=round(f1, 3)))

    out = pd.DataFrame(rows)
    wide = out.pivot(index="rule", columns="threshold", values=["P", "R", "F1"])
    print(wide.to_string())
    out.to_csv(os.path.join(HERE, "..", "rq2q_incl_possibly.csv"), index=False)
    print("wrote rq2q_incl_possibly.csv")


if __name__ == "__main__":
    main()
