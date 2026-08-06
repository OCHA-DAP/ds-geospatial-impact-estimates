"""RQ2l — recall by CEMS's OWN damage grade: Damaged vs Destroyed (flag #12).

User question (2026-07-27): CEMS has grades (1 Possibly / 2 Damaged / 3 Destroyed). We
score vs 2+3. Does performance differ by grade? This is the CEMS-native analogue of the
ChatMap grade-slope: for each product, recall of DESTROYED (class 3) vs DAMAGED (class 2)
points. Expectation: destroyed found much better — satellite = destruction detector.

Precision is not grade-specific (a flag matches "any" damage), so we report RECALL by
grade. Core region (rq5b), gold centroids OSU v0-pinned, r=10 m.

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2l_cems_grade_recall.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
R = 10
MEMBERS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
           "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}


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
    df = gp.building_flags(columns=["lon", "lat", *MEMBERS.values()])  # OSU v0-pinned
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    region = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    for a in (gp.dissolve_union(gp.microsoft_aoi()), gp.dissolve_union(gp.impact_v2_aoi()),
              gp.dissolve_union(gp.osu_aoi()), uh_aoi(),
              gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                            "analysed_extent.parquet"))):
        region = region.intersection(a)

    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.geometry.within(region)]
    dam = cems[cems.damage_class == 2]   # Damaged
    des = cems[cems.damage_class == 3]   # Destroyed
    tree_dam = cKDTree(np.c_[dam.geometry.x, dam.geometry.y])
    tree_des = cKDTree(np.c_[des.geometry.x, des.geometry.y])
    print(f"core region | Damaged (class 2): {len(dam):,} | Destroyed (class 3): {len(des):,}")

    rows = []
    for nm, col in MEMBERS.items():
        fl = bld[bld.geometry.within(region) & (bld[col].to_numpy(dtype="float64", na_value=0.0) == 1)]
        xy = np.c_[fl.geometry.x, fl.geometry.y]
        tree_fl = cKDTree(xy)
        # PRECISION per grade: share of the product's flags within r of a Damaged / Destroyed point
        P_dam = (tree_dam.query(xy, k=1)[0] <= R).mean()
        P_des = (tree_des.query(xy, k=1)[0] <= R).mean()
        # RECALL per grade: share of Damaged / Destroyed points with a flag within r
        R_dam = (tree_fl.query(np.c_[dam.geometry.x, dam.geometry.y], k=1)[0] <= R).mean()
        R_des = (tree_fl.query(np.c_[des.geometry.x, des.geometry.y], k=1)[0] <= R).mean()
        rows.append(dict(product=nm, n_flags=len(fl),
                         P_vs_damaged=round(float(P_dam), 3),
                         P_vs_destroyed=round(float(P_des), 3),
                         R_of_damaged=round(float(R_dam), 3),
                         R_of_destroyed=round(float(R_des), 3)))
        print(rows[-1])

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq2l_cems_grade_recall.csv"), index=False)
    print("wrote rq2l_cems_grade_recall.csv")
    print("\nP_vs_X = share of the product's flags within 10 m of a class-X point")
    print("R_of_X = share of class-X points with a product flag within 10 m")


if __name__ == "__main__":
    main()
