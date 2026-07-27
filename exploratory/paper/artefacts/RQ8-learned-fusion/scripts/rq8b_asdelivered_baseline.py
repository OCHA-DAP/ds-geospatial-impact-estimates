"""RQ8b — does the day-zero baseline beat the products in the AS-DELIVERED frame?

User hypothesis (2026-07-27): on the full delivered footprint (all CEMS AOIs, junk zones
included) the day-zero model (coast + density + ShakeMap) may outperform the products
outright, because products blanket-flag low-damage AOIs and geography would not.
Counter-mechanism: Caracas has high density + high MMI, so two of three day-zero inputs
vote "flag".

Design: fusion frame (gold centroids OSU v0-pinned; label = CEMS {2,3} within 20 m).
For each product, region = union(CEMS latest extents) ∩ product extent (UNEP: all AOIs,
coverage assumption). Within each region: day-zero RF (same spec as RQ8) with spatial
block CV (GroupKFold, H3 res-7) -> AP; product binary flag -> AP; plus binary
comparison at matched flag count (P/R of product vs day-zero rule of the same size).

Run: uv run --group etl --with scipy --with scikit-learn --with matplotlib python \
       exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8b_asdelivered_baseline.py
"""
from __future__ import annotations
import io, json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.spatial import cKDTree
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold
from sklearn.metrics import average_precision_score

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
POS = (2, 3)
LABEL_R = 20
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

    all_ext = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    d = bld[bld.geometry.within(all_ext)].copy().reset_index(drop=True)
    print(f"buildings in union of CEMS extents: {len(d):,}")

    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    ct = cKDTree(np.c_[cems.geometry.x, cems.geometry.y])
    d["y"] = (ct.query(np.c_[d.geometry.x, d.geometry.y], k=1)[0] <= LABEL_R).astype(int)

    # day-zero features, built once on the superset
    ll = d.to_crs(4326)
    d["cell7"] = [h3.latlng_to_cell(p.y, p.x, 7) for p in ll.geometry]
    cell9 = pd.Series([h3.latlng_to_cell(p.y, p.x, 9) for p in ll.geometry])
    d["density9"] = cell9.map(cell9.value_counts())
    coast = gp.to_metric(gp.codab(0)).geometry.make_valid().union_all().boundary
    d["dist_coast"] = d.geometry.distance(coast) / 1000.0
    frames = []
    for ev in ("us6000t7zp", "us6000t7zc"):
        raw = json.loads(stratus.load_blob_data(
            gp.S.blob_path("bronze", "source=usgs", "adm0=VE", f"event={ev}", "cont_mi.json"),
            stage="dev", container_name=gp.S.container))
        g = gpd.GeoDataFrame.from_features(raw["features"], crs=4326).to_crs(gp.METRIC_CRS)
        frames.append(g[["value", "geometry"]])
    mmi = np.full(len(d), np.nan)
    for g in frames:
        j = gpd.sjoin_nearest(d[["geometry"]], g, how="left")
        j = j[~j.index.duplicated()]
        mmi = np.fmax(mmi, j["value"].to_numpy())
    d["mmi"] = np.nan_to_num(mmi, nan=np.nanmedian(mmi))

    prod_aois = {"MS": gp.dissolve_union(gp.microsoft_aoi()),
                 "IMPACT": gp.dissolve_union(gp.impact_v2_aoi()),
                 "OSU": gp.dissolve_union(gp.osu_aoi()),
                 "UH": uh_aoi(),
                 "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                                       "analysed_extent.parquet")),
                 "UNEP": None}

    CONTEXT = ["density9", "dist_coast", "mmi"]
    rows = []
    for nm, col in MEMBERS.items():
        sel = (np.ones(len(d), bool) if prod_aois[nm] is None
               else d.geometry.within(prod_aois[nm]).to_numpy())
        sub = d[sel]
        y = sub.y.to_numpy()
        flags = sub[col].to_numpy(dtype="float64", na_value=0.0)
        X = sub[CONTEXT].astype(float).to_numpy()
        groups = sub.cell7.to_numpy()
        oof = np.zeros(len(sub))
        gkf = GroupKFold(n_splits=5)
        for tr, te in gkf.split(X, y, groups):
            m = RandomForestClassifier(n_estimators=400, min_samples_leaf=20,
                                       class_weight="balanced_subsample", n_jobs=-1,
                                       random_state=884)
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            m.fit((X[tr] - mu) / sd, y[tr])
            oof[te] = m.predict_proba((X[te] - mu) / sd)[:, 1]
        ap_geo = average_precision_score(y, oof)
        ap_prod = average_precision_score(y, flags)
        nflag = int(flags.sum())
        tp = int(((flags == 1) & (y == 1)).sum())
        thr = np.partition(oof, -nflag)[-nflag]
        gsel = oof >= thr
        gtp = int((gsel & (y == 1)).sum())
        rows.append(dict(
            product=nm, n_bld=len(sub), n_pos=int(y.sum()), n_flags=nflag,
            AP_product=round(ap_prod, 3), AP_dayzero=round(ap_geo, 3),
            P_product=round(tp / max(nflag, 1), 3),
            R_product=round(tp / max(int(y.sum()), 1), 3),
            P_dayzero_matched=round(gtp / max(int(gsel.sum()), 1), 3),
            R_dayzero_matched=round(gtp / max(int(y.sum()), 1), 3)))
        print(rows[-1])

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq8b_asdelivered_baseline.csv"), index=False)
    print("wrote rq8b_asdelivered_baseline.csv")


if __name__ == "__main__":
    main()
