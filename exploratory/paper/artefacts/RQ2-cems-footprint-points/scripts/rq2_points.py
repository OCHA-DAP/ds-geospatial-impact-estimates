"""RQ2 — sources vs CEMS damage POINTS (builtUpP) — the primary performance analysis.

Dual-anchored pairwise native matching (RQ0 DESIGN): CEMS points stay native; each product keeps
its own footprints. Precision and recall come from opposite anchors, so no shared building universe
or true-negative count is needed:
  recall    = CEMS damage points with a product-flagged building within r / CEMS points (in prod AOI)
  precision = product-flagged buildings with a CEMS point within r / product buildings (in shared region)
  F1        = harmonic mean
Coverage: recall region = product AOI; precision region = CEMS(point-product) analysed extent ∩ AOI.
Distances point-to-footprint in EPSG:32619 (containment ⇒ distance 0). r ∈ {5,10,20} m.
Thresholds: headline positive = {Damaged(2), Destroyed(3)}; also reported incl. Possibly(1).

Run: uv run --group etl python exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2_points.py
"""
from __future__ import annotations
import os, sys
import geopandas as gpd
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

FIGS = os.path.join(os.path.dirname(__file__), "..", "figs")
os.makedirs(FIGS, exist_ok=True)
RADII = [5, 10, 20]
THRESHOLDS = {"dmg+destroyed": (2, 3), "incl_possibly": (1, 2, 3)}


def _match_rate(left, right, r):
    """Fraction of `left` features with a `right` feature within r metres (containment ⇒ 0)."""
    if len(left) == 0 or len(right) == 0:
        return 0, len(left)
    l = left.reset_index(drop=True).reset_index(names="_lid")
    m = gpd.sjoin_nearest(l[["_lid", "geometry"]], right[["geometry"]],
                          max_distance=r, how="inner", distance_col="_d")
    return m["_lid"].nunique(), len(l)


def load_products():
    out = {}
    out["Microsoft"] = (gp.to_metric(gp.microsoft()), gp.dissolve_union(gp.microsoft_aoi()))
    out["IMPACT v2"] = (gp.to_metric(gp.impact_v2()), gp.dissolve_union(gp.impact_v2_aoi()))
    out["OSU"] = (gp.to_metric(gp.osu()), gp.dissolve_union(gp.osu_aoi()))
    for k, (g, _) in out.items():
        print(f"  {k}: {len(g)} damaged footprints")
    return out


def main():
    pts_all = gp.to_metric(gp.cems_points())
    ext = gp.cems_extent()
    ext_latest = gp.to_metric(ext[ext.is_latest == True]).geometry.make_valid().union_all()  # noqa: E712
    print(f"CEMS points: {len(pts_all)} | latest analysed-extent AOIs: "
          f"{sorted(ext[ext.is_latest == True].aoi.unique().tolist())}")
    prods = load_products()

    rows = []
    for name, (foot, aoi) in prods.items():
        region = ext_latest.intersection(aoi)                 # shared coverage (precision)
        foot_in = foot[foot.geometry.representative_point().within(region)]
        for tname, classes in THRESHOLDS.items():
            cems_pos = pts_all[pts_all.damage_class.isin(classes)]
            cems_in_aoi = cems_pos[cems_pos.within(aoi)]        # CEMS pts in product AOI
            cems_in_region = cems_pos[cems_pos.within(region)]  # STRICT overlap (both looked)
            leak = len(cems_in_aoi) - len(cems_in_region)       # pts in AOI but outside CEMS extent
            if leak:
                print(f"    [{name}|{tname}] LEAK: {leak} CEMS pts in AOI but outside CEMS extent "
                      f"(aoi={len(cems_in_aoi)} region={len(cems_in_region)})")
            for r in RADII:
                tp_r, n_pts = _match_rate(cems_in_region, foot_in, r)   # recall anchor (strict overlap)
                tp_p, n_prod = _match_rate(foot_in, cems_in_region, r)  # precision anchor
                recall = tp_r / n_pts if n_pts else float("nan")
                prec = tp_p / n_prod if n_prod else float("nan")
                f1 = (2 * prec * recall / (prec + recall)) if (prec + recall) else float("nan")
                rows.append(dict(product=name, threshold=tname, radius_m=r,
                                 cems_pts=n_pts, recall=round(recall, 3),
                                 prod_bldgs=n_prod, precision=round(prec, 3),
                                 f1=round(f1, 3)))
                print(f"  [{name}|{tname}|r={r:>2}] R={recall:.3f} ({tp_r}/{n_pts})  "
                      f"P={prec:.3f} ({tp_p}/{n_prod})  F1={f1:.3f}")

    df = pd.DataFrame(rows)
    out_csv = os.path.join(os.path.dirname(__file__), "..", "rq2_points_summary.csv")
    df.to_csv(out_csv, index=False)
    print("\n== headline (dmg+destroyed, r=10 m) ==")
    print(df[(df.threshold == "dmg+destroyed") & (df.radius_m == 10)].to_string(index=False))
    print("wrote", out_csv)

    head = df[(df.threshold == "dmg+destroyed") & (df.radius_m == 10)]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    head.set_index("product")[["precision", "recall", "f1"]].plot.bar(ax=ax, rot=0)
    ax.set_title("Sources vs CEMS damage points (dual-anchor, {Damaged,Destroyed}, r=10 m)")
    ax.set_ylim(0, 1); ax.set_ylabel("score")
    fig.tight_layout(); fig.savefig(os.path.join(FIGS, "rq2_pr_f1_r10.png"), dpi=130)
    print("wrote figs/rq2_pr_f1_r10.png")


if __name__ == "__main__":
    main()
