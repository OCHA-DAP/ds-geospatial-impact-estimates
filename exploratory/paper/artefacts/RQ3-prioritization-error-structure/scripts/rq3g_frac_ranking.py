"""RQ3g — area ranking by damage FRACTION vs damage COUNT (external review question).

The published ranking (RQ3/RQ3f) ranks cells by damaged-building COUNT. The reviewer
question: does that flatter geography, since counts partly rank building stock, and
would rates (damage fraction) tell a different urban-vs-rural story? This mirrors
rq3f_null_ranking.py exactly (same regions, resolutions, null construction, activity
filter) and adds per cell: building stock, CEMS damaged fraction, product flagged
fraction, null mean probability. Rankings compared:
    count : Spearman(cems_count, product_count)   — the published quantity
    frac  : Spearman(cems_count/n_bld, product_flags/n_bld), cells with >= MIN_BLD buildings
Null enters both (expected count = sum of predicted p; expected rate = mean p).
Scope 'all' (as-delivered union, res 8 and 7), the manuscript's primary ranking frame.

ANCHOR: the count columns must reproduce rq3f_null_ranking.csv exactly (all products,
both resolutions) or the script raises.

Run: uv run --group etl --with scikit-learn --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3g_frac_ranking.py
"""
from __future__ import annotations
import json, os, sys

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "..", "figs")
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

POS = (2, 3)
LABEL_R = 10
RESOS = (8, 7)
MIN_BLD = 20  # frac ranking only: cells below this are rate noise (1/3 = 33%)
FLAGS = {"Microsoft": "ms_dmg", "IMPACT v2": "sar_dmg", "OSU": "osu_dmg",
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
    df = gp.building_flags(columns=["lon", "lat", *FLAGS.values()])
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)

    ext = gp.cems_extent()
    ext_latest = gp.to_metric(ext[ext.is_latest == True]  # noqa: E712
                              ).geometry.make_valid().union_all()
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]

    d = bld[bld.geometry.within(ext_latest)].copy().reset_index(drop=True)
    ct = cKDTree(np.c_[cems.geometry.x, cems.geometry.y])
    d["y"] = (ct.query(np.c_[d.geometry.x, d.geometry.y], k=1)[0] <= LABEL_R).astype(int)

    ll = d.to_crs(4326)
    for _r in {7, *RESOS}:
        d[f"cell{_r}"] = [h3.latlng_to_cell(p.y, p.x, _r) for p in ll.geometry]
    cell9 = pd.Series([h3.latlng_to_cell(p.y, p.x, 9) for p in ll.geometry])
    d["density9"] = cell9.map(cell9.value_counts()).to_numpy()
    coast = gp.to_metric(gp.codab(0)).geometry.make_valid().union_all().boundary
    d["dist_coast"] = d.geometry.distance(coast) / 1000.0
    frames = []
    for ev in ("us6000t7zp", "us6000t7zc"):
        raw = json.loads(stratus.load_blob_data(
            gp.S.blob_path("bronze", "source=usgs", "adm0=VE", f"event={ev}", "cont_mi.json",
                           event=None),  # frozen VE layout: 'event=' is a literal segment
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
            "UNEP": None}
    CONTEXT = ["density9", "dist_coast", "mmi"]

    rows, scat = [], {}
    for name, col in FLAGS.items():
        region = ext_latest if aois[name] is None else ext_latest.intersection(aois[name])
        sub = d[d.geometry.within(region).to_numpy()].copy()
        X = sub[CONTEXT].astype(float).to_numpy()
        y = sub.y.to_numpy()
        groups = sub.cell7.to_numpy()
        oof = np.zeros(len(sub))
        for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            m = LogisticRegression(max_iter=2000, class_weight="balanced")
            m.fit((X[tr] - mu) / sd, y[tr])
            oof[te] = m.predict_proba((X[te] - mu) / sd)[:, 1]
        sub["null_p"] = oof
        sub["pdmg"] = sub[col].to_numpy(dtype="float64", na_value=0.0)

        cs = cems[cems.geometry.representative_point().within(region)]
        cll = cs.to_crs(4326).geometry.representative_point()

        for res in RESOS:
            ccol = f"cell{res}"
            cems_cnt = pd.Series([h3.latlng_to_cell(p.y, p.x, res)
                                  for p in cll]).value_counts().rename("cems")
            agg = sub.groupby(ccol).agg(pdmg=("pdmg", "sum"), null=("null_p", "sum"),
                                        n_bld=(ccol, "size"))
            t = pd.concat([cems_cnt, agg], axis=1).fillna(0)

            # ---- count ranking (rq3f verbatim: activity filter) ----
            both = t[(t.cems > 0) | (t.pdmg > 0)]
            rho_c, _ = spearmanr(both.cems, both.pdmg)
            rho_cn, _ = spearmanr(both.cems, both.null)

            # ---- fraction ranking (cells with real stock; same activity filter) ----
            fr = t[(t.n_bld >= MIN_BLD) & ((t.cems > 0) | (t.pdmg > 0))].copy()
            fr["cems_fr"] = fr.cems / fr.n_bld
            fr["pdmg_fr"] = fr.pdmg / fr.n_bld
            fr["null_fr"] = fr.null / fr.n_bld  # mean predicted probability
            rho_f, _ = spearmanr(fr.cems_fr, fr.pdmg_fr)
            rho_fn, _ = spearmanr(fr.cems_fr, fr.null_fr)

            rows.append(dict(res=res, product=name,
                             cells_count=len(both), cells_frac=len(fr),
                             rho_count=round(rho_c, 3), rho_null_count=round(rho_cn, 3),
                             rho_frac=round(rho_f, 3), rho_null_frac=round(rho_fn, 3)))
            print(rows[-1])
            if res == 8:
                scat[name] = fr

    out = pd.DataFrame(rows)

    # ---- anchor: count columns must reproduce the frozen rq3f CSV exactly ----
    ref = pd.read_csv(os.path.join(HERE, "..", "rq3f_null_ranking.csv")
                      ).set_index(["res", "product"])
    bad = []
    for _, r in out.iterrows():
        want = ref.loc[(r.res, r["product"])]
        for got, w, nm in ((r.rho_count, want.rho_product, "rho_count"),
                           (r.rho_null_count, want.rho_null, "rho_null"),
                           (r.cells_count, want.cells, "cells")):
            if got != w:
                bad.append(f"{r['product']} res{r.res} {nm}: got {got}, frozen {w}")
    if bad:
        raise SystemExit("ANCHOR FAILED vs rq3f_null_ranking.csv:\n  " + "\n  ".join(bad))
    print("anchor OK: count ranking reproduces rq3f_null_ranking.csv exactly")

    out.to_csv(os.path.join(HERE, "..", "rq3g_frac_vs_count.csv"), index=False)
    print("\nwrote rq3g_frac_vs_count.csv")

    # ---- fig 1: paired rho comparison, count vs frac (both resolutions) ----
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharey=True)
    for ax, res in zip(axes, RESOS):
        v = out[out.res == res].reset_index(drop=True)
        yp = np.arange(len(v))
        ax.scatter(v.rho_count, yp, s=90, color="#1b4f8a", zorder=3, label="ranked by COUNT")
        ax.scatter(v.rho_frac, yp, s=90, color="#c98a1e", zorder=3, marker="s",
                   label="ranked by FRACTION (cells ≥20 bldgs)")
        ax.scatter(v.rho_null_count, yp, s=60, facecolor="white", edgecolor="#1b4f8a",
                   zorder=3, label="geography null (count)")
        ax.scatter(v.rho_null_frac, yp, s=60, facecolor="white", edgecolor="#c98a1e",
                   marker="s", zorder=3, label="geography null (fraction)")
        for i, r in v.iterrows():
            ax.plot([r.rho_frac, r.rho_count], [i, i], color="#c9d2d4", lw=2, zorder=1)
        ax.set_yticks(yp, v["product"], fontsize=11)
        ax.axvline(0, color="#999", lw=0.8)
        km2 = {8: "0.74", 7: "5.2"}[res]
        ax.set_title(f"res {res} (~{km2} km² cells)", fontsize=12)
        ax.set_xlabel("Spearman ρ vs CEMS", fontsize=11)
        ax.grid(axis="x", alpha=0.25)
    axes[0].legend(fontsize=9, loc="lower left", frameon=False)
    fig.suptitle("Area ranking by damage COUNT vs damage FRACTION (as-delivered scope)",
                 fontsize=13)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq3g_frac_vs_count_rho.png"), dpi=150)
    print("wrote figs/rq3g_frac_vs_count_rho.png")

    # ---- fig 2: scatter grid, CEMS fraction vs product fraction (res 8) ----
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    for ax, (name, fr) in zip(axes.flat, scat.items()):
        ax.scatter(fr.cems_fr, fr.pdmg_fr, s=14, alpha=0.5, color="#2a78d6")
        rho = out[(out.res == 8) & (out["product"] == name)].rho_frac.iloc[0]
        ax.set_title(f"{name}  (ρ = {rho:.2f}, n = {len(fr)})", fontsize=12)
        ax.set_xlabel("CEMS damaged fraction", fontsize=10)
        ax.set_ylabel("product flagged fraction", fontsize=10)
    fig.suptitle("Damage FRACTION per ~0.74 km² cell: product vs CEMS "
                 f"(cells with ≥{MIN_BLD} buildings, as-delivered scope)", fontsize=13)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq3g_frac_scatter_res8.png"), dpi=150)
    print("wrote figs/rq3g_frac_scatter_res8.png")


if __name__ == "__main__":
    main()
