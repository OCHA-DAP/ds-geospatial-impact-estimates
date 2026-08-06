"""RQ3 — prioritization skill & error structure (the thesis test).

RQ2 showed high recall / low precision (heavy over-detection). The question: given that, do the
products still RANK areas correctly for triage? And is the over-detection spatially uniform (noise
-> ranking survives) or structured (bias -> ranking corrupted)?

Aggregate to H3 cells (res 8 ~0.74 km2, and res 7 ~5.2 km2) within each product's STRICT shared
region (CEMS extent ∩ product AOI). Per cell: CEMS damage count ({Damaged,Destroyed}) and product
damaged count. Then:
  Prioritization skill : Spearman & Kendall rank corr (cems vs product per cell); top-k concordance.
  Error structure      : over-detection ratio (product/cems) distribution; does it scale with CEMS
                         density (Spearman ratio~cems) -> a bias signature vs flat noise.

Run: uv run --group etl python exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3_prioritization.py
"""
from __future__ import annotations
import os, sys
import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr, kendalltau
import h3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

FIGS = os.path.join(os.path.dirname(__file__), "..", "figs")
os.makedirs(FIGS, exist_ok=True)
POS = (2, 3)  # headline CEMS positive classes


def _cell(lat, lng, res):
    return h3.latlng_to_cell(lat, lng, res)  # h3 v4


def _h3_counts(gdf_metric, region, res):
    """Filter to region (metric), reproject to 4326, count features per H3 cell."""
    sub = gdf_metric[gdf_metric.geometry.representative_point().within(region)]
    if len(sub) == 0:
        return pd.Series(dtype=int)
    ll = sub.to_crs(4326).geometry.representative_point()
    cells = [_cell(p.y, p.x, res) for p in ll]
    return pd.Series(cells).value_counts()


def products():
    return {
        "Microsoft": (gp.to_metric(gp.microsoft()), gp.dissolve_union(gp.microsoft_aoi())),
        "IMPACT v2": (gp.to_metric(gp.impact_v2()), gp.dissolve_union(gp.impact_v2_aoi())),
        "OSU": (gp.to_metric(gp.osu()), gp.dissolve_union(gp.osu_aoi())),
    }


def main():
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    ext = gp.cems_extent()
    ext_latest = gp.to_metric(ext[ext.is_latest == True]).geometry.make_valid().union_all()  # noqa: E712
    prods = products()

    rows, scatter = [], {}
    for res in (8, 7):
        for name, (foot, aoi) in prods.items():
            region = ext_latest.intersection(aoi)
            c = _h3_counts(cems, region, res).rename("cems")
            p = _h3_counts(foot, region, res).rename("pdmg")
            df = pd.concat([c, p], axis=1).fillna(0)
            both = df[(df.cems > 0) | (df.pdmg > 0)]
            dmg = df[df.cems > 0]  # cells CEMS flags as damaged
            rho, _ = spearmanr(both.cems, both.pdmg)
            tau, _ = kendalltau(both.cems, both.pdmg)
            # top-k concordance: overlap of top-k cells by each ranking
            def topk(k):
                a = set(df.cems.sort_values(ascending=False).head(k).index)
                b = set(df.pdmg.sort_values(ascending=False).head(k).index)
                return len(a & b) / k
            # over-detection ratio on CEMS-damaged cells; does it scale with CEMS count?
            ratio = (dmg.pdmg / dmg.cems)
            rho_bias, _ = spearmanr(dmg.cems, ratio) if len(dmg) > 2 else (np.nan, np.nan)
            rows.append(dict(res=res, product=name, cells=len(both), cems_cells=len(dmg),
                             spearman=round(rho, 3), kendall=round(tau, 3),
                             top10=round(topk(10), 2), top20=round(topk(20), 2),
                             top50=round(topk(50), 2),
                             overdet_median=round(ratio.median(), 1),
                             overdet_p90=round(ratio.quantile(.9), 1),
                             bias_rho=round(rho_bias, 3)))
            if res == 8:
                scatter[name] = (both.cems.values, both.pdmg.values, rho)
            print(f"  res{res} {name:10s} cells={len(both):5d} rho={rho:.3f} tau={tau:.3f} "
                  f"top10={topk(10):.2f} top20={topk(20):.2f} "
                  f"overdet_med={ratio.median():.1f} bias_rho={rho_bias:.3f}")

    out = pd.DataFrame(rows)
    csv = os.path.join(os.path.dirname(__file__), "..", "rq3_prioritization_summary.csv")
    out.to_csv(csv, index=False)
    print("\n== res 8 ==\n", out[out.res == 8].to_string(index=False))
    print("== res 7 ==\n", out[out.res == 7].to_string(index=False))
    print("wrote", csv)

    fig, ax = plt.subplots(1, 3, figsize=(13, 4.2))
    for i, (name, (x, y, rho)) in enumerate(scatter.items()):
        ax[i].scatter(x + 0.5, y + 0.5, s=8, alpha=.4)
        ax[i].set_xscale("log"); ax[i].set_yscale("log")
        ax[i].set_title(f"{name}  (ρ={rho:.2f})")
        ax[i].set_xlabel("CEMS damage / H3 cell"); ax[i].set_ylabel("product damage / cell")
    fig.suptitle("RQ3 prioritization — per-H3 (res 8) CEMS vs product damage counts")
    fig.tight_layout(); fig.savefig(os.path.join(FIGS, "rq3_rank_scatter_res8.png"), dpi=130)
    print("wrote figs/rq3_rank_scatter_res8.png")


if __name__ == "__main__":
    main()
