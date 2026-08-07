"""RQ3f — does the GEOGRAPHY NULL rank areas as well as the products do?

The gap this closes: RQ3 established that products rank areas far better than they identify
buildings, and that ranking is the paper's one positive finding about them. But the null model
(coast distance + building density + ShakeMap) was never tested at area level. If it ranks
just as well, the products add nothing at ANY scale and the positive finding collapses too.

Method mirrors rq3_prioritization.py exactly so the numbers are directly comparable: same
regions (CEMS latest extent ∩ product AOI), same H3 resolutions (7 and 8), same Spearman of
per-cell CEMS damage count vs predictor. The null's per-cell value is the SUM of its
out-of-fold predicted probabilities over buildings in that cell — its expected damage count —
which needs no threshold. Null is the logistic (the stronger learner; see manuscript Methods),
fitted with the same spatial-block CV (GroupKFold over H3 res-7).

Run: uv run --group etl --with scikit-learn --with scipy python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3f_null_ranking.py
"""
from __future__ import annotations
import json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
POS = (2, 3)
LABEL_R = 10  # paper's primary frame

# GIE_SCOPE=caraballeda restricts every region to the Caraballeda AOI. This is the sharper
# test: across all CEMS extents, 96% of the damage sits in Caraballeda, so "rank the areas"
# largely reduces to "find Caraballeda" — which coastal+dense geography does trivially. The
# question that matters is whether the products can out-rank geography WITHIN the damage zone.
# Caraballeda holds too few ~5 km2 cells for a meaningful correlation, so this mode uses
# finer resolutions.
SCOPE = os.environ.get("GIE_SCOPE", "all")  # all | caraballeda | core
RESOS = (9, 8) if SCOPE in ("caraballeda", "core") else (8, 7)
SUF = "" if SCOPE == "all" else f"_{SCOPE}"
# All six evaluated members. RQ3 originally covered only MS/IMPACT/OSU (the members whose
# extents were available then); UH, LIST and UNEP are added here using the same AOI
# definitions as the as-delivered analysis (rq8b), so the null test covers the full set.
FLAGS = {"Microsoft": "ms_dmg", "IMPACT v2": "sar_dmg", "OSU": "osu_dmg",
         "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}


def uh_aoi():
    """UH has no published extent; approximate it from its own classified footprints
    (res-9 cells dilated by one ring) — same construction as rq8/rq8b."""
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
    df = gp.building_flags(columns=["lon", "lat", *FLAGS.values()])  # OSU v0-pinned
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)

    ext = gp.cems_extent()
    lat = ext[ext.is_latest == True]  # noqa: E712
    if SCOPE == "caraballeda":
        lat = lat[lat.aoi_name == "Caraballeda"]
    ext_latest = gp.to_metric(lat).geometry.make_valid().union_all()
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]

    d = bld[bld.geometry.within(ext_latest)].copy().reset_index(drop=True)
    ct = cKDTree(np.c_[cems.geometry.x, cems.geometry.y])
    d["y"] = (ct.query(np.c_[d.geometry.x, d.geometry.y], k=1)[0] <= LABEL_R).astype(int)

    # context features (identical construction to the fusion analysis)
    ll = d.to_crs(4326)
    d["cell7"] = [h3.latlng_to_cell(p.y, p.x, 7) for p in ll.geometry]
    for _r in RESOS:
        if _r != 7:
            d[f"cell{_r}"] = [h3.latlng_to_cell(p.y, p.x, _r) for p in ll.geometry]
    cell9 = pd.Series([h3.latlng_to_cell(p.y, p.x, 9) for p in ll.geometry])
    d["density9"] = cell9.map(cell9.value_counts()).to_numpy()
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

    aois = {"Microsoft": gp.dissolve_union(gp.microsoft_aoi()),
            "IMPACT v2": gp.dissolve_union(gp.impact_v2_aoi()),
            "OSU": gp.dissolve_union(gp.osu_aoi()),
            "UH": uh_aoi(),
            "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                                  "analysed_extent.parquet")),
            "UNEP": None}  # UNEP: all CEMS AOIs (coverage assumption, as in rq8b)
    CONTEXT = ["density9", "dist_coast", "mmi"]

    if SCOPE == "core":
        # The paper's core region: CEMS latest extents intersected with ALL five
        # extent-publishing products' AOIs (UNEP has none: coverage assumption). One
        # shared region for every product, so the null has a single score per res.
        core = ext_latest
        for a in [v for v in aois.values() if v is not None]:
            core = core.intersection(a)
        if core.is_empty:
            raise RuntimeError("core-region intersection came out empty")
        ext_latest = core
        aois = {name: None for name in aois}

    rows = []
    for name, col in FLAGS.items():
        region = ext_latest if aois[name] is None else ext_latest.intersection(aois[name])
        sel = d.geometry.within(region).to_numpy()
        sub = d[sel].copy()
        X = sub[CONTEXT].astype(float).to_numpy()
        y = sub.y.to_numpy()
        groups = sub.cell7.to_numpy()

        # out-of-fold null probabilities, spatially blocked
        oof = np.zeros(len(sub))
        for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            m = LogisticRegression(max_iter=2000, class_weight="balanced")
            m.fit((X[tr] - mu) / sd, y[tr])
            oof[te] = m.predict_proba((X[te] - mu) / sd)[:, 1]
        sub["null_p"] = oof
        sub["pdmg"] = sub[col].to_numpy(dtype="float64", na_value=0.0)

        # CEMS damage count per cell, in the same region
        cs = cems[cems.geometry.representative_point().within(region)]
        cll = cs.to_crs(4326).geometry.representative_point()

        for res in RESOS:
            ccol = f"cell{res}"
            cems_cnt = pd.Series([h3.latlng_to_cell(p.y, p.x, res)
                                  for p in cll]).value_counts().rename("cems")
            agg = sub.groupby(ccol).agg(pdmg=("pdmg", "sum"), null=("null_p", "sum"))
            t = pd.concat([cems_cnt, agg], axis=1).fillna(0)
            # core scope: one FIXED cell set (every building-bearing cell of the shared
            # region), identical for all products, so the null has a single score.
            # Other scopes keep the original activity filter.
            both = t if SCOPE == "core" else t[(t.cems > 0) | (t.pdmg > 0)]
            rho_p, _ = spearmanr(both.cems, both.pdmg)
            rho_n, _ = spearmanr(both.cems, both.null)

            def topk(colname, k):
                a = set(t.cems.sort_values(ascending=False).head(k).index)
                b = set(t[colname].sort_values(ascending=False).head(k).index)
                return len(a & b) / k

            rows.append(dict(res=res, product=name, cells=len(both),
                             rho_product=round(rho_p, 3), rho_null=round(rho_n, 3),
                             delta=round(rho_p - rho_n, 3),
                             top20_product=round(topk("pdmg", 20), 2),
                             top20_null=round(topk("null", 20), 2)))
            print(rows[-1])

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", f"rq3f_null_ranking{SUF}.csv"), index=False)
    print("\n" + out.to_string(index=False))
    print(f"\nwrote rq3f_null_ranking{SUF}.csv")
    print("\nINTERPRETATION: delta > 0 means the product ranks areas better than geography alone.")


if __name__ == "__main__":
    main()
