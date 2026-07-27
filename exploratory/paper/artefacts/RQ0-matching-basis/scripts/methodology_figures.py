"""Paper methodology figures: (1) coverage & intersection, (2) dual-anchor matching.

Fig 1  coverage — the La Guaira / Caraballeda coast: CEMS analysed strip ∩ product AOI = the scoring
        region, with CEMS damage grades; a locator inset shows the regional swaths + epicentre.
Fig 2  dual-anchor matching — a Caraballeda window: product footprints classified TP/FP vs CEMS
        points classified matched/FN at r=10 m. The confusion matrix, in space (OSU: recall-rich,
        precision-poor -> a sea of FP with most CEMS points matched).

Run: uv run --group etl --with contextily python .../RQ0-matching-basis/scripts/methodology_figures.py
"""
from __future__ import annotations
import os, sys
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle
from matplotlib.lines import Line2D
import contextily as cx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

FIGS = os.path.join(os.path.dirname(__file__), "..", "figs")
os.makedirs(FIGS, exist_ok=True)
WM = 3857
GRADE = {1: "#f9c74f", 2: "#f3722c", 3: "#a4133c"}
GLAB = {1: "Possibly damaged", 2: "Damaged", 3: "Destroyed"}
SRC = {"IMPACT v2": "#8452a1", "OSU": "#2a9d8f"}
EPI = gpd.GeoSeries([Point(-68.4716, 10.4351)], crs=4326).to_crs(WM)


def _base(ax, src=cx.providers.CartoDB.Positron):
    try:
        cx.add_basemap(ax, source=src, attribution_size=5)
    except Exception as e:
        print("  (basemap skipped:", e, ")")


def _wm(lon0, lat0, lon1, lat1):
    return gpd.GeoSeries([box(lon0, lat0, lon1, lat1)], crs=4326).to_crs(WM).total_bounds


def _scalebar(ax, length_m, label):
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    x = x0 + (x1 - x0) * 0.06; y = y0 + (y1 - y0) * 0.07
    ax.plot([x, x + length_m], [y, y], color="k", lw=3, solid_capstyle="butt", zorder=8)
    ax.text(x + length_m / 2, y + (y1 - y0) * 0.014, label, ha="center", va="bottom",
            fontsize=8, zorder=8)


def load():
    d = {}
    d["cems"] = gp.cems_points().to_crs(WM)
    ext = gp.cems_extent()
    d["ext"] = ext[ext.is_latest == True].to_crs(WM)  # noqa: E712
    d["osu"] = gp.osu().to_crs(WM)
    d["microsoft"] = gp.microsoft().to_crs(WM)
    d["aoi"] = {"IMPACT v2": gp.impact_v2_aoi().to_crs(WM), "OSU": gp.osu_aoi().to_crs(WM),
                "Microsoft": gp.microsoft_aoi().to_crs(WM)}
    return d


def fig_coverage(d):
    fig, ax = plt.subplots(figsize=(12, 6.2))
    x0, y0, x1, y1 = _wm(-67.06, 10.566, -66.80, 10.632)
    d["aoi"]["OSU"].plot(ax=ax, facecolor=SRC["OSU"], alpha=.09, edgecolor=SRC["OSU"], lw=1)
    d["ext"].plot(ax=ax, facecolor="#e63946", edgecolor="#9d0208", alpha=.24, lw=1.3)
    for g in (1, 2, 3):
        d["cems"][d["cems"].damage_class == g].plot(ax=ax, color=GRADE[g], markersize=11,
                                                    alpha=.92, edgecolor="white", lw=.25,
                                                    label=GLAB[g])
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    _base(ax)
    ax.set_title("Scoring region = CEMS analysed extent ∩ product AOI\nLa Guaira – Caraballeda coast, "
                 "CEMS damage grades", fontsize=12.5, loc="left")
    leg1 = ax.legend(loc="lower right", fontsize=9, framealpha=.93, title="CEMS grade")
    ax.add_artist(leg1)
    ax.legend(handles=[Patch(facecolor=SRC["OSU"], alpha=.3, label="product analysed AOI (OSU)"),
                       Patch(facecolor="#e63946", alpha=.4, label="CEMS analysed extent (reference)")],
              loc="upper right", fontsize=9, framealpha=.93)
    ax.set_xticks([]); ax.set_yticks([]); _scalebar(ax, 5000, "5 km")

    ins = ax.inset_axes([0.015, 0.60, 0.36, 0.38])
    lx0, ly0, lx1, ly1 = _wm(-68.75, 10.28, -66.72, 10.74)
    for name in ("IMPACT v2", "OSU"):
        d["aoi"][name].plot(ax=ins, facecolor=SRC[name], alpha=.20, edgecolor="none")
    d["ext"].plot(ax=ins, color="#e63946", alpha=.95, lw=0)
    EPI.plot(ax=ins, marker="*", color="#ffb703", markersize=200, edgecolor="k", lw=.9, zorder=6)
    ins.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor="k", lw=1.6))
    ins.set_xlim(lx0, lx1); ins.set_ylim(ly0, ly1); _base(ins)
    ins.set_xticks([]); ins.set_yticks([])
    ins.set_title("regional context — swaths, epicentre ★, zoom box", fontsize=7.5)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_coverage_intersection.png"), dpi=165, bbox_inches="tight")
    print("wrote figs/fig_coverage_intersection.png")


def _dense_window(cems_wm, half_m):
    c12 = cems_wm[cems_wm.aoi_number == 12]
    gx = (c12.geometry.x / 500).round() * 500
    gy = (c12.geometry.y / 500).round() * 500
    cx0, cy0 = pd.Series(list(zip(gx, gy))).value_counts().idxmax()
    return cx0 - half_m, cy0 - half_m, cx0 + half_m, cy0 + half_m


def fig_matching(d, product="OSU", half_m=250):
    x0, y0, x1, y1 = _dense_window(d["cems"], half_m)
    W = box(x0, y0, x1, y1)
    # restrict to the product's analysed AOI so FN / negatives are only counted where it looked
    paoi = d["aoi"][product].geometry.make_valid().union_all()
    Wc = W.intersection(paoi)
    # building stock (the negatives) in the window ∩ coverage, for context
    wll = gpd.GeoSeries([W], crs=WM).to_crs(4326).total_bounds
    stock = gp.overture_window(*wll).to_crs(WM)
    stock = stock[stock.representative_point().within(Wc)]
    foot = d[product.lower()][d[product.lower()].intersects(Wc)].copy()
    cem = d["cems"][(d["cems"].damage_class.isin((2, 3))) & (d["cems"].within(Wc))].copy()
    fm = foot.to_crs(32619).reset_index(drop=True).reset_index(names="_i")
    cm = cem.to_crs(32619).reset_index(drop=True).reset_index(names="_j")
    ftp = set(gpd.sjoin_nearest(fm[["_i", "geometry"]], cm[["geometry"]], max_distance=10,
                                how="inner")["_i"])
    ctp = set(gpd.sjoin_nearest(cm[["_j", "geometry"]], fm[["geometry"]], max_distance=10,
                                how="inner")["_j"])
    foot["cls"] = ["TP" if i in ftp else "FP" for i in range(len(foot))]
    cem["cls"] = ["match" if j in ctp else "FN" for j in range(len(cem))]

    fig, ax = plt.subplots(figsize=(9, 8.6))
    stock.plot(ax=ax, facecolor="#c9ccd1", edgecolor="#a8abb0", lw=.3, alpha=.7, zorder=1)
    foot[foot.cls == "FP"].plot(ax=ax, facecolor="#e76f51", edgecolor="#a83a22", lw=.4, alpha=.7, zorder=2)
    foot[foot.cls == "TP"].plot(ax=ax, facecolor="#2a9d8f", edgecolor="#186b5f", lw=.5, alpha=.9, zorder=3)
    cem[cem.cls == "match"].plot(ax=ax, color="#0b132b", markersize=44, edgecolor="w", lw=1.1, zorder=6)
    cem[cem.cls == "FN"].plot(ax=ax, color="none", markersize=66, edgecolor="#d00000", lw=2.1, zorder=6)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); _base(ax)
    n, tp, fn = len(foot), (foot.cls == "TP").sum(), (cem.cls == "FN").sum()
    rc = (cem.cls == "match").sum()
    ax.set_title(f"Dual-anchor matching — how TP / FP / FN / TN are defined ({product} vs CEMS, r=10 m)\n"
                 f"Illustrative window, Caraballeda (local TP={tp} FP={n-tp} FN={fn}); "
                 f"AOI-wide metrics in RQ2", fontsize=11, loc="left")
    ax.legend(handles=[
        Patch(facecolor="#c9ccd1", label="building — not flagged by product (negative)"),
        Patch(facecolor="#2a9d8f", label="footprint — TP (≤10 m from CEMS)"),
        Patch(facecolor="#e76f51", label="footprint — FP (over-detection)"),
        Line2D([], [], marker="o", color="w", markerfacecolor="#0b132b", markeredgecolor="w",
               markersize=11, label="CEMS point — matched (recall)"),
        Line2D([], [], marker="o", color="w", markerfacecolor="none", markeredgecolor="#d00000",
               markersize=12, markeredgewidth=2, label="CEMS point — missed (FN)")],
        loc="lower right", fontsize=8.5, framealpha=.93)
    ax.set_xticks([]); ax.set_yticks([]); _scalebar(ax, 100, "100 m")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_dual_anchor_matching.png"), dpi=170, bbox_inches="tight")
    print("wrote figs/fig_dual_anchor_matching.png")


def main():
    d = load()
    fig_coverage(d)
    fig_matching(d, product="Microsoft", half_m=250)


if __name__ == "__main__":
    main()
