"""RQ3h — does multi-model AGREEMENT improve area ranking? (external review question)

The paper's closing recommendation ("do not spend time choosing a product; spend it
counting agreement") is proven at building level only; the reviewer asked whether it
holds for ranking, where singles already do well. This ranks core-region cells by the
combination predictors and compares them with the frozen single-product/null results:
    singles      count of flagged buildings per cell        (anchor vs rq3f core CSV)
    geog. null   sum of OOF predicted p (expected count)    (anchor vs rq3f core CSV)
    vote sum     per-cell sum of vote counts (0-6/building) — the continuous dial
    k-of-6       count of buildings with >= k votes, k=1..6 — @tbl-dial's rules as cells
    fusion       per-cell sum of the OOF weighted-fusion p  — expected count, same
                 construction as the null, so directly comparable
Frame: rq3f GIE_SCOPE=core verbatim (fixed shared cell set, res 9 and 8). The null is
re-fitted here exactly as rq3f fits it (same features, same spatial-block CV) so the
anchor is exact; votes and fusion come from the frozen rq8 OOF parquet, joined by
coordinates (asserted 1:1). A damage-fraction variant of every predictor is included
(cells with >= 20 buildings), extending RQ3g's check to the combinations.

ANCHOR: rho/top-20 for the six singles and the null must reproduce
rq3f_null_ranking_core.csv exactly, or the script raises.

Run: uv run --group etl --with scikit-learn --with scipy python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3h_agreement_ranking.py
"""
from __future__ import annotations
import json, os, sys

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
RQ8 = os.path.join(HERE, "..", "..", "RQ8-learned-fusion")
POS = (2, 3)
LABEL_R = 10
RESOS = (9, 8)  # rq3f core-scope resolutions
MIN_BLD = 20    # fraction variant only
FLAGS = {"Microsoft": "ms_dmg", "IMPACT v2": "sar_dmg", "OSU": "osu_dmg",
         "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}
PARQ_COL = {"Microsoft": "flag_MS", "IMPACT v2": "flag_IMPACT", "OSU": "flag_OSU",
            "UH": "flag_UH", "LIST": "flag_LIST", "UNEP": "flag_UNEP"}


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
    df = gp.building_flags(columns=["lon", "lat", *FLAGS.values()])
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)

    ext = gp.cems_extent()
    ext_latest = gp.to_metric(ext[ext.is_latest == True]  # noqa: E712
                              ).geometry.make_valid().union_all()
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]

    core = ext_latest
    for a in (gp.dissolve_union(gp.microsoft_aoi()), gp.dissolve_union(gp.impact_v2_aoi()),
              gp.dissolve_union(gp.osu_aoi()), uh_aoi(),
              gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                            "analysed_extent.parquet"))):
        core = core.intersection(a)
    d = bld[bld.geometry.within(core)].copy().reset_index(drop=True)

    ct = cKDTree(np.c_[cems.geometry.x, cems.geometry.y])
    d["y"] = (ct.query(np.c_[d.geometry.x, d.geometry.y], k=1)[0] <= LABEL_R).astype(int)

    # ---- join the frozen rq8 OOF scores (fusion) and flags by coordinates ----
    pq = pd.read_parquet(os.path.join(RQ8, "rq8_oof_scores_r10.parquet"))
    if len(pq) != len(d):
        raise SystemExit(f"core-region mismatch: script {len(d):,} vs parquet {len(pq):,}")
    d["k7"] = (d.lon.round(7).astype(str) + "|" + d.lat.round(7).astype(str))
    pq["k7"] = (pq.lon.round(7).astype(str) + "|" + pq.lat.round(7).astype(str))
    m = d.merge(pq[["k7", "fusion_logit", *PARQ_COL.values()]], on="k7", how="left")
    if m.fusion_logit.isna().any():
        raise SystemExit(f"coordinate join incomplete: {int(m.fusion_logit.isna().sum())} unmatched")
    d = m
    for nm, col in FLAGS.items():  # gold flags and parquet flags must agree
        a = d[col].to_numpy(dtype="float64", na_value=0.0) == 1
        b = d[PARQ_COL[nm]].to_numpy(dtype="float64") == 1
        if (a != b).any():
            raise SystemExit(f"flag mismatch after join: {nm}")
    votes = d[list(PARQ_COL.values())].sum(axis=1).to_numpy()

    # ---- context features + spatially blocked logistic null (rq3f verbatim) ----
    ll = d.geometry.to_crs(4326) if hasattr(d, "geometry") else None
    d = gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d.lon, d.lat), crs=4326).to_crs(gp.METRIC_CRS)
    ll = d.to_crs(4326)
    d["cell7"] = [h3.latlng_to_cell(p.y, p.x, 7) for p in ll.geometry]
    for _r in RESOS:
        d[f"cell{_r}"] = [h3.latlng_to_cell(p.y, p.x, _r) for p in ll.geometry]
    cell9 = pd.Series([h3.latlng_to_cell(p.y, p.x, 9) for p in ll.geometry])
    d["density9"] = cell9.map(cell9.value_counts()).to_numpy()
    coast = gp.to_metric(gp.codab(0)).geometry.make_valid().union_all().boundary
    d["dist_coast"] = d.geometry.distance(coast) / 1000.0
    frames = []
    for ev in ("us6000t7zp", "us6000t7zc"):
        raw = json.loads(stratus.load_blob_data(
            gp.S.blob_path("bronze", "source=usgs", "adm0=VE", f"event={ev}", "cont_mi.json",
                           event=None), stage="dev", container_name=gp.S.container))
        g = gpd.GeoDataFrame.from_features(raw["features"], crs=4326).to_crs(gp.METRIC_CRS)
        frames.append(g[["value", "geometry"]])
    mmi = np.full(len(d), np.nan)
    for g in frames:
        j = gpd.sjoin_nearest(d[["geometry"]], g, how="left")
        j = j[~j.index.duplicated()]
        mmi = np.fmax(mmi, j["value"].to_numpy())
    d["mmi"] = np.nan_to_num(mmi, nan=np.nanmedian(mmi))

    X = d[["density9", "dist_coast", "mmi"]].astype(float).to_numpy()
    y = d.y.to_numpy()
    groups = d.cell7.to_numpy()
    oof = np.zeros(len(d))
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        mdl = LogisticRegression(max_iter=2000, class_weight="balanced")
        mdl.fit((X[tr] - mu) / sd, y[tr])
        oof[te] = mdl.predict_proba((X[te] - mu) / sd)[:, 1]
    d["null_p"] = oof

    # ---- per-cell aggregation and ranking ----
    cs = cems[cems.geometry.representative_point().within(core)]
    cll = cs.to_crs(4326).geometry.representative_point()

    preds = {nm: (d[col].to_numpy(dtype="float64", na_value=0.0) == 1).astype(float)
             for nm, col in FLAGS.items()}
    preds["geography null"] = d.null_p.to_numpy()
    preds["vote sum"] = votes.astype(float)
    for k in range(1, 7):
        preds[f"{k}-of-6"] = (votes >= k).astype(float)
    preds["weighted fusion"] = d.fusion_logit.to_numpy()

    ref = pd.read_csv(os.path.join(HERE, "..", "rq3f_null_ranking_core.csv")
                      ).set_index(["res", "product"])
    rows, bad = [], []
    for res in RESOS:
        ccol = f"cell{res}"
        cems_cnt = pd.Series([h3.latlng_to_cell(p.y, p.x, res)
                              for p in cll]).value_counts().rename("cems")
        base = d.groupby(ccol).size().rename("n_bld")
        t = pd.concat([cems_cnt, base], axis=1).fillna(0)  # fixed shared cell set
        t = t[t.n_bld > 0]

        def topk(series, k=20):
            a = set(t.cems.sort_values(ascending=False).head(k).index)
            b = set(series.sort_values(ascending=False).head(k).index)
            return len(a & b) / k

        def topk_exp(series, k=20):
            """Tie-aware expected top-k overlap: cells strictly above the boundary
            score count fully; cells tied AT the boundary each enter with probability
            (remaining slots / tie-group size) — the average over all fair tie-breaks.
            Identical to topk() when the boundary is untied (continuous scores)."""
            truth = set(t.cems.sort_values(ascending=False).head(k).index)
            s = series.sort_values(ascending=False)
            cut = s.iloc[k - 1]
            safe = s[s > cut].index
            tied = s[s == cut].index
            slots = k - len(safe)
            exp = len(truth & set(safe)) + len(truth & set(tied)) * slots / len(tied)
            return exp / k

        fr_mask = t.n_bld >= MIN_BLD
        for nm, v in preds.items():
            s = pd.Series(v, index=d[ccol]).groupby(level=0).sum().reindex(t.index).fillna(0)
            rho, _ = spearmanr(t.cems, s)
            t20 = topk(s)
            fr = (t.cems / t.n_bld)[fr_mask]
            sf = (s / t.n_bld)[fr_mask]
            rho_f, _ = spearmanr(fr, sf)
            rows.append(dict(res=res, predictor=nm, cells=len(t),
                             rho=round(rho, 3), top20=round(t20, 2),
                             top20_exp=round(topk_exp(s), 2),
                             rho_frac=round(rho_f, 3), cells_frac=int(fr_mask.sum())))
            print(rows[-1])
            # anchor for singles and null
            key = "geography null" if nm == "geography null" else nm
            if nm in FLAGS or nm == "geography null":
                anchor_nm = list(FLAGS)[0] if nm == "geography null" else nm
                want = ref.loc[(res, anchor_nm)]
                w_rho = want.rho_null if nm == "geography null" else want.rho_product
                w_t20 = want.top20_null if nm == "geography null" else want.top20_product
                got_rho, got_t20 = round(rho, 3), round(t20, 2)
                if got_rho != w_rho or got_t20 != w_t20:
                    bad.append(f"{nm} res{res}: rho {got_rho} vs {w_rho}, top20 {got_t20} vs {w_t20}")

    if bad:
        raise SystemExit("ANCHOR FAILED vs rq3f_null_ranking_core.csv:\n  " + "\n  ".join(bad))
    print("anchor OK: singles and null reproduce rq3f_null_ranking_core.csv exactly")

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq3h_agreement_ranking.csv"), index=False)
    print("\n" + out.pivot(index="predictor", columns="res", values=["rho", "top20", "rho_frac"])
          .to_string())
    print("wrote rq3h_agreement_ranking.csv")


if __name__ == "__main__":
    main()
