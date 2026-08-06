"""RQ2o — does UH reproduce Microsoft's west-Caraballeda failure cluster?

Motivation (2026-08-06): the UH authors confirmed their analysis ran on VANTOR imagery
exclusively — the same commercial source as Microsoft's failing single-scene west strip
(RQ2g). If UH, on the same vendor's imagery over the same strip, does NOT over-flag there,
that is a cross-product control for the west-cluster diagnosis: the failure was Microsoft's
per-scene model calibration, not the imagery. (Caveat: "same vendor" is not "same scene" —
UH's acquisition dates are unconfirmed.)

Test: within the Caraballeda CEMS AOI ∩ each product's extent, split at lon -67.03 (the
RQ2g scene boundary) and compare flag share + CEMS precision (r = 10 m) per side, for UH
and for Microsoft.

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2o_uh_west_strip.py
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
POS = (2, 3)
R = 10
SPLIT_LON = -67.03  # RQ2g scene boundary


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


def main() -> None:
    df = gp.building_flags(columns=["lon", "lat", "uh_dmg", "ms_dmg"])  # OSU pin irrelevant here
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)

    ext = gp.to_metric(gp.cems_extent().query("is_latest"))
    cara = ext[ext.aoi_name == "Caraballeda"].geometry.make_valid().union_all()
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]

    aois = {"UH": uh_aoi(), "MS": gp.dissolve_union(gp.microsoft_aoi())}
    rows = []
    for nm, aoi in aois.items():
        col = {"UH": "uh_dmg", "MS": "ms_dmg"}[nm]
        reg = cara.intersection(aoi)
        inb = bld[bld.geometry.within(reg)].copy()
        lon = inb.geometry.to_crs(4326).x
        for side, mask in (("west", lon < SPLIT_LON), ("east", lon >= SPLIT_LON)):
            sub = inb[mask]
            if not len(sub):
                continue
            fl = sub[sub[col].to_numpy(dtype="float64", na_value=0.0) == 1]
            ca = cems[cems.geometry.within(reg)]
            ca = ca[(ca.geometry.to_crs(4326).x < SPLIT_LON) == (side == "west")]
            p = np.nan
            if len(fl) and len(ca):
                ct = cKDTree(np.c_[ca.geometry.x, ca.geometry.y])
                p = float((ct.query(np.c_[fl.geometry.x, fl.geometry.y], k=1)[0] <= R).mean())
            rows.append(dict(product=nm, side=side, n_bld=len(sub), n_flags=len(fl),
                             flag_share=round(len(fl) / len(sub), 3), n_cems=len(ca),
                             P_cems=round(p, 3) if p == p else np.nan))
            print(rows[-1])

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq2o_uh_west_strip.csv"), index=False)
    print("wrote rq2o_uh_west_strip.csv")


if __name__ == "__main__":
    main()
