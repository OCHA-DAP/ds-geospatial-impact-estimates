"""RQ2k — precision against CEMS alone vs CEMS UNION ChatMap field points.

User question (2026-07-27): combining CEMS with the ChatMap field data should raise the
metrics slightly — is it captured? It wasn't. This computes it directly. A flagged
building is a true positive if a CEMS {2,3} point OR a ChatMap field point lies within
r; this can only raise precision (field points are real damage CEMS may have missed).
The ChatMap analogue of the MapSwipe crowd-adjustment, using the independent ground
reference instead of the crowd.

Core region (rq5b: CEMS latest ∩ five product AOIs); gold centroids, OSU v0-pinned; r=10 m.

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2k_field_union_precision.py
"""
from __future__ import annotations
import json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
POS = (2, 3)
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
    import ocha_stratus as stratus
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
    cems = cems[cems.damage_class.isin(POS)]
    cpts = cems[cems.geometry.within(region)][["geometry"]]
    field = gpd.GeoDataFrame.from_features(json.loads(stratus.load_blob_data(
        gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE", "hdx",
                       "chatmap_field_validated_damage_points.geojson"),
        stage="dev", container_name=gp.S.container))["features"], crs=4326).to_crs(gp.METRIC_CRS)
    fpts = field[field.geometry.within(region)][["geometry"]]
    truth = np.r_[np.c_[cpts.geometry.x, cpts.geometry.y],
                  np.c_[fpts.geometry.x, fpts.geometry.y]]
    print(f"core region | CEMS {{2,3}} pts {len(cpts):,} | ChatMap field pts {len(fpts):,} "
          f"| union {len(truth):,}")
    tree_c = cKDTree(np.c_[cpts.geometry.x, cpts.geometry.y])
    tree_u = cKDTree(truth)

    rows = []
    for nm, col in MEMBERS.items():
        fl = bld[bld.geometry.within(region) & (bld[col].to_numpy(dtype="float64", na_value=0.0) == 1)]
        xy = np.c_[fl.geometry.x, fl.geometry.y]
        p_cems = (tree_c.query(xy, k=1)[0] <= R).mean()
        p_union = (tree_u.query(xy, k=1)[0] <= R).mean()
        rows.append(dict(product=nm, n_flags=len(fl),
                         P_cems=round(float(p_cems), 3),
                         P_cems_plus_field=round(float(p_union), 3),
                         abs_gain=round(float(p_union - p_cems), 3),
                         rel_gain=f"+{(p_union/p_cems - 1)*100:.0f}%" if p_cems else "n/a"))
        print(rows[-1])

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq2k_field_union_precision.csv"), index=False)
    print("wrote rq2k_field_union_precision.csv")


if __name__ == "__main__":
    main()
