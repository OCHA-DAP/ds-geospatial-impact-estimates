"""Area ranking: how well each predictor orders H3 cells by damage, against the geography
null, as rows of the results table. One module replaces rq3f (three scopes) and rq3h.

Cells lens (rq3f): per scope (as delivered, core, Caraballeda) and per product, Spearman ρ of
the product's flagged count per cell against the CEMS count, the same for a spatially
cross-validated logistic geography null (building density, coast distance, ShakeMap MMI),
and the top-20 overlap. The null's features are built once over all buildings inside the
scope's CEMS extent, so the core and Caraballeda scopes see identical features.
Cells-agreement lens (rq3h): the core region's fixed cell set, all predictors including the
k-of-6 rules and the vote sum; the fusion score is included only when the frozen rq8
out-of-fold parquet is present (--with-fusion).
"""
from __future__ import annotations

import json
import os
import sys

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paperlib as pl  # noqa: E402
from paperlib import gp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = "pipeline/ranking.py"
LABEL_R = 10
LONG = {"MS": "Microsoft", "IMPACT": "IMPACT v2", "OSU": "OSU", "UH": "UH", "LIST": "LIST", "UNEP": "UNEP"}
SCOPES = {"asd": (8, 7), "core": (9, 8), "Caraballeda": (9, 8)}   # scope -> H3 resolutions
MIN_BLD = 20
USGS_EVENTS = ("us6000t7zp", "us6000t7zc")


def rows(region, lens, radius, predictor, **metrics):
    return [dict(region=region, lens=lens, radius=radius, predictor=predictor, metric=m, value=v, source=SOURCE)
            for m, v in metrics.items() if v is not None and not (isinstance(v, float) and np.isnan(v))]


def context_features(d: gpd.GeoDataFrame, resos) -> gpd.GeoDataFrame:
    """density9, dist_coast, mmi and the cell ids the null and the aggregation need."""
    import ocha_stratus as stratus
    d = d.copy()
    ll = pl.location(d).to_crs(4326)
    d["cell7"] = [h3.latlng_to_cell(p.y, p.x, 7) for p in ll]
    for r in set(resos) - {7}:
        d[f"cell{r}"] = [h3.latlng_to_cell(p.y, p.x, r) for p in ll]
    cell9 = pd.Series([h3.latlng_to_cell(p.y, p.x, 9) for p in ll])
    d["density9"] = cell9.map(cell9.value_counts()).to_numpy()
    coast = gp.to_metric(gp.codab(0)).geometry.make_valid().union_all().boundary
    d["dist_coast"] = d.geometry.distance(coast) / 1000.0
    mmi = np.full(len(d), np.nan)
    for ev in USGS_EVENTS:
        raw = json.loads(stratus.load_blob_data(gp.S.blob_path("bronze", "source=usgs", "adm0=VE", f"event={ev}", "cont_mi.json", event=None),
                                                stage="dev", container_name=gp.S.container))
        g = gpd.GeoDataFrame.from_features(raw["features"], crs=4326).to_crs(pl.METRIC_CRS)[["value", "geometry"]]
        j = gpd.sjoin_nearest(d[["geometry"]], g, how="left"); j = j[~j.index.duplicated()]
        mmi = np.fmax(mmi, j["value"].to_numpy())
    d["mmi"] = np.nan_to_num(mmi, nan=np.nanmedian(mmi))
    return d


def null_oof(sub: pd.DataFrame) -> np.ndarray:
    """Out-of-fold geography-null probability, 5-fold grouped by res-7 cell."""
    X = sub[["density9", "dist_coast", "mmi"]].astype(float).to_numpy()
    y, groups = sub.y.to_numpy(), sub.cell7.to_numpy()
    oof = np.zeros(len(sub))
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        m = LogisticRegression(max_iter=2000, class_weight="balanced").fit((X[tr] - mu) / sd, y[tr])
        oof[te] = m.predict_proba((X[te] - mu) / sd)[:, 1]
    return oof


def cems_counts(cems, region, res) -> pd.Series:
    cs = cems[cems.geometry.representative_point().within(region)]
    ll = cs.to_crs(4326).geometry.representative_point()
    return pd.Series([h3.latlng_to_cell(p.y, p.x, res) for p in ll]).value_counts().rename("cems")


def topk(truth: pd.Series, s: pd.Series, k=20) -> float:
    a = set(truth.sort_values(ascending=False).head(k).index)
    b = set(s.sort_values(ascending=False).head(k).index)
    return len(a & b) / k


def topk_exp(truth: pd.Series, s: pd.Series, k=20) -> float:
    """Tie-aware expected top-k overlap (cells tied at the boundary share the remaining slots)."""
    tr = set(truth.sort_values(ascending=False).head(k).index)
    s = s.sort_values(ascending=False); cut = s.iloc[k - 1]
    safe, tied = s[s > cut].index, s[s == cut].index
    return (len(tr & set(safe)) + len(tr & set(tied)) * (k - len(safe)) / len(tied)) / k


def scope_frame(scope: str):
    """Buildings inside the scope's CEMS extent, labelled and with context features."""
    b = pl.buildings()
    ext = gp.cems_extent().query("is_latest")
    if scope == "Caraballeda":
        ext = ext[ext.aoi_name == "Caraballeda"]
    ext_latest = gp.to_metric(ext).geometry.make_valid().union_all()
    cems = pl.reference("floor")
    d = b[pl.in_region(b, ext_latest)].copy().reset_index(drop=True)
    d["y"] = gp.within_r(d, cems, LABEL_R).astype(int)
    d = context_features(d, SCOPES[scope])
    return d, ext_latest, cems


def cells(scope: str) -> list:
    """rq3f: per product region (scope ∩ product AOI; the core scope uses one shared region)."""
    d, ext_latest, cems = scope_frame(scope)
    aois = dict(pl.product_aois()); aois["UNEP"] = None
    if scope == "core":
        ext_latest = pl.core_region()
        aois = {p: None for p in aois}
    out = []
    for p, col in pl.PRODUCTS.items():
        region = ext_latest if aois[p] is None else ext_latest.intersection(aois[p])
        sub = d[pl.in_region(d, region)].copy()
        sub["null_p"] = null_oof(sub)
        sub["pdmg"] = sub[col].astype(float)
        for res in SCOPES[scope]:
            agg = sub.groupby(f"cell{res}").agg(pdmg=("pdmg", "sum"), null=("null_p", "sum"))
            t = pd.concat([cems_counts(cems, region, res), agg], axis=1).fillna(0)
            both = t if scope == "core" else t[(t.cems > 0) | (t.pdmg > 0)]
            rho_p, rho_n = spearmanr(both.cems, both.pdmg)[0], spearmanr(both.cems, both.null)[0]
            out += rows(scope, "cells", res, LONG[p], rho=round(rho_p, 3), rho_null=round(rho_n, 3), delta=round(rho_p - rho_n, 3),
                        top20=round(topk(t.cems, t.pdmg), 2), top20_null=round(topk(t.cems, t.null), 2), cells=len(both))
    return out


def cells_agreement(with_fusion: bool) -> list:
    """rq3h: the core's fixed cell set; products, geography null, vote sum, k-of-6 (and fusion)."""
    d, _, cems = scope_frame("core")
    core = pl.core_region()
    d = d[pl.in_region(d, core)].copy().reset_index(drop=True)
    d["null_p"] = null_oof(d)
    preds = {LONG[p]: d[c].astype(float).to_numpy() for p, c in pl.PRODUCTS.items()}
    preds["geography null"] = d.null_p.to_numpy()
    preds["vote sum"] = d.votes.astype(float).to_numpy()
    for k in range(1, 7):
        preds[f"{k}-of-6"] = (d.votes >= k).astype(float).to_numpy()
    if with_fusion:
        pq = pd.read_parquet(os.path.join(HERE, "..", "artefacts", "RQ8-learned-fusion", "rq8_oof_scores_r10.parquet"))
        m = d[["id"]].merge(pq[["id", "fusion_logit"]], on="id", how="left")
        if m.fusion_logit.isna().any():
            raise SystemExit("fusion join incomplete: rq8 parquet does not cover the core buildings")
        preds["weighted fusion"] = m.fusion_logit.to_numpy()
    out = []
    for res in SCOPES["core"]:
        ccol = f"cell{res}"
        t = pd.concat([cems_counts(cems, core, res), d.groupby(ccol).size().rename("n_bld")], axis=1).fillna(0)
        t = t[t.n_bld > 0]
        fr_mask = t.n_bld >= MIN_BLD
        for nm, v in preds.items():
            s = pd.Series(v, index=d[ccol]).groupby(level=0).sum().reindex(t.index).fillna(0)
            rho_f = spearmanr((t.cems / t.n_bld)[fr_mask], (s / t.n_bld)[fr_mask])[0]
            out += rows("core", "cells-agreement", res, nm, rho=round(spearmanr(t.cems, s)[0], 3), top20=round(topk(t.cems, s), 2),
                        top20_exp=round(topk_exp(t.cems, s), 2), rho_frac=round(rho_f, 3), cells=len(t), cells_frac=int(fr_mask.sum()))
    return out


def main():
    with_fusion = "--with-fusion" in sys.argv[1:]
    out = []
    for scope in SCOPES:
        print(f"== cells {scope}", flush=True); out += cells(scope)
    print("== cells-agreement core", flush=True); out += cells_agreement(with_fusion)
    res = pd.DataFrame(out)
    res.to_csv(os.path.join(HERE, "results_ranking.csv"), index=False)
    print(f"results_ranking.csv: {len(res)} rows")


if __name__ == "__main__":
    main()
