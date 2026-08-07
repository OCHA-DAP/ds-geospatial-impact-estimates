"""RQ7 figure — how MapSwipe crowd adjustment enters the precision calculation.

Building-scale window in the Catia La Mar strip (MapSwipe rounds 1=3179 and 2=3248,
identical res-11 task cells; round 2 is POST-FREEZE and opted into explicitly here).
Mirrors the rq2i mechanism exactly: flags = gold centroids (ms_dmg), TP = CEMS grade-2/3
point within 10 m, crowd verdict = majority (argmax of vote shares) of the flag's res-11
cell, confirmation = majority "Yes"; flags in un-voted cells are outside the crowd sample
(rq2i extrapolates the confirmed rate onto them).

Panel A: round-1 verdicts, annotated with the four flag fates. Panel B: round-2 verdicts,
cells whose confirmation status flipped outlined. Footer: strip-wide flag-level rates for
both rounds (the numbers in rq7_round2_replication.csv).

Writes figs/rq7_crowd_adjustment_explainer.png (window chosen deterministically).
Run: uv run --group etl --with matplotlib python \
       exploratory/paper/artefacts/RQ7-mapswipe-validation/scripts/rq7_round2_explainer_fig.py
"""
from __future__ import annotations

import gzip
import json
import os
import sys

import geopandas as gpd
import h3
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import Polygon

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402
import ocha_stratus as stratus  # noqa: E402

FIGS = os.path.join(os.path.dirname(__file__), "..", "figs")
os.makedirs(FIGS, exist_ok=True)
M = gp.METRIC_CRS  # UTM 19N
R_MATCH = 10.0

C_HIT, C_CONF, C_FP = "#2e7d32", "#2a78d6", "#ff7f0e"          # validated (CVD dE 11.3)
T_YES, T_NO, T_UNSURE = "#d9e8f8", "#f4e3d5", "#e9e9e9"        # cell tints
C_FLIP = "#8452a1"


def load_tasks():
    """Both rounds' per-cell majorities, keyed by res-11 h3. 0=No 1=Yes 2=Unsure."""
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    out = {}
    for label, pid in (("r1", "3179"), ("r2", "3248")):
        pref = gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE", f"project={pid}")
        names = [b.name for b in cc.list_blobs(name_starts_with=pref)
                 if "agg_results_by_task" in b.name and b.name.endswith(".geojson.gz")]
        if len(names) != 1:
            raise RuntimeError(f"expected one agg export for project {pid}, got {names}")
        t = pd.DataFrame([f["properties"] for f in json.loads(
            gzip.decompress(cc.download_blob(names[0]).readall()))["features"]])
        if "0_share" not in t.columns:  # 2-option round: derive the implicit "No" zeros
            t["0_count"] = t["total_count"] - t["1_count"] - t["2_count"]
            if (t["0_count"] < 0).any():
                raise RuntimeError(f"project {pid}: 0_count derivation invalid")
            t["0_share"] = t["0_count"] / t["total_count"]
        t = t.set_index("h3")
        out[label] = pd.Series(
            t[["0_share", "1_share", "2_share"]].to_numpy().argmax(axis=1), index=t.index)
    if set(out["r1"].index) != set(out["r2"].index):
        raise RuntimeError("rounds do not cover identical task cells")
    return out["r1"], out["r2"]


def load_flags_and_cems():
    df = gp.building_flags(columns=["lon", "lat", "ms_dmg"])
    ms = df[df["ms_dmg"].to_numpy(dtype="float64", na_value=0.0) == 1.0]
    flags = gpd.GeoDataFrame(ms[["id"]],
                             geometry=gpd.points_from_xy(ms.lon, ms.lat), crs=4326)
    cems = gp.cems_points()
    cems = cems[cems.damage_class.isin((2, 3))].copy()
    return flags, cems


def main():
    maj1, maj2 = load_tasks()
    flags, cems = load_flags_and_cems()

    ll = flags.geometry
    flags["cell11"] = [h3.latlng_to_cell(p.y, p.x, 11) for p in ll]
    flags["m1"] = flags["cell11"].map(maj1)   # NaN = cell not crowd-voted
    flags["m2"] = flags["cell11"].map(maj2)

    fm = flags.to_crs(M)
    cm = cems.to_crs(M)
    cm["geometry"] = cm.geometry.representative_point()
    near = gpd.sjoin_nearest(fm, cm[["geometry"]], how="left", distance_col="d")
    flags["hit"] = (near.groupby(near.index)["d"].min() <= R_MATCH).values

    strip = flags[flags["m1"].notna()].copy()      # flags inside the two campaigns' cells
    un = strip[~strip["hit"]]
    stats = {
        "strip_flags": len(strip), "strip_hits": int(strip["hit"].sum()),
        "unmatched": len(un),
        "conf_r1": float((un["m1"] == 1).mean()),
        "conf_r2": float((un["m2"] == 1).mean()),
    }
    print("STRIP:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in stats.items()})

    # ---- window search: confirmation-flip cells with CEMS + flag variety nearby
    cells = pd.DataFrame({"m1": maj1, "m2": maj2})
    cells["lat"], cells["lng"] = zip(*[h3.cell_to_latlng(c) for c in cells.index])
    gcells = gpd.GeoDataFrame(cells, geometry=gpd.points_from_xy(cells.lng, cells.lat),
                              crs=4326).to_crs(M)
    flip = gcells[(gcells.m1 == 1) != (gcells.m2 == 1)]
    fx, fy = fm.geometry.x.values, fm.geometry.y.values
    cx_, cy_ = cm.geometry.x.values, cm.geometry.y.values
    W, Hh = 260.0, 200.0                            # half-extents (m)
    best, best_score = None, -1
    hit_mask = flags["hit"].values
    conf1 = (flags["m1"] == 1).values & ~hit_mask
    rej1 = (flags["m1"] == 0).values & ~hit_mask
    for _, c in flip.iterrows():
        x, y = c.geometry.x, c.geometry.y
        inw = (np.abs(fx - x) < W) & (np.abs(fy - y) < Hh)
        ncems = int(((np.abs(cx_ - x) < W) & (np.abs(cy_ - y) < Hh)).sum())
        score = (min(ncems, 3) * 10 + min(int((conf1 & inw).sum()), 3) * 6
                 + min(int((rej1 & inw).sum()), 4) * 3 + min(int((hit_mask & inw).sum()), 2) * 8
                 + min(int(inw.sum()), 25))
        if ncems >= 1 and (conf1 & inw).sum() >= 1 and (rej1 & inw).sum() >= 2 \
                and inw.sum() >= 10 and score > best_score:
            best, best_score = (x, y), score
    if best is None:
        raise RuntimeError("no window satisfies the criteria — relax the search")
    x0, x1, y0, y1 = best[0] - W, best[0] + W, best[1] - Hh, best[1] + Hh
    print(f"window (UTM19N): x {x0:.0f}..{x1:.0f}  y {y0:.0f}..{y1:.0f}  score {best_score}")

    # ---- context footprints
    wgs = gpd.GeoSeries([Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])],
                        crs=M).to_crs(4326).total_bounds
    foot = gp.overture_window(*wgs).to_crs(M)
    if len(foot) == 0:
        raise RuntimeError("overture window empty — wrong bbox?")
    print(f"context footprints: {len(foot)}")

    # cell polygons intersecting window
    pad = 60
    keep = gcells[(gcells.geometry.x > x0 - pad) & (gcells.geometry.x < x1 + pad)
                  & (gcells.geometry.y > y0 - pad) & (gcells.geometry.y < y1 + pad)]
    polys = gpd.GeoDataFrame(
        keep[["m1", "m2"]],
        geometry=[Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)])
                  for c in keep.index], crs=4326).to_crs(M)

    inw_f = flags[(fx > x0) & (fx < x1) & (fy > y0) & (fy < y1)].copy()
    inw_fm = fm.loc[inw_f.index]
    inw_c = cm[(cx_ > x0) & (cx_ < x1) & (cy_ > y0) & (cy_ < y1)]

    fig, axes = plt.subplots(1, 2, figsize=(15.5, 8.6))
    tint = {0: T_NO, 1: T_YES, 2: T_UNSURE}
    for ax, mcol, ttl in (
            (axes[0], "m1",
             "A · round 1 (≈6 votes/cell): how each unmatched flag is adjudicated"),
            (axes[1], "m2",
             "B · round 2 (≈16 votes/cell, no “No damage” option): same cells re-voted")):
        for _, r in polys.iterrows():
            v = r[mcol]
            ax.add_patch(plt.Polygon(np.asarray(r.geometry.exterior.coords),
                                     fc=tint.get(v, "white"), ec="#cccccc", lw=.5, zorder=1))
        foot.plot(ax=ax, fc="#d8d4cd", ec="#b8b4ad", lw=.3, zorder=2)
        verd = inw_f[mcol]
        cat = np.where(inw_f["hit"], "hit",
              np.where(verd == 1, "conf", np.where(verd.isna(), "nocrowd", "fp")))
        examples = {}
        for key, fc, edge, lw in (("fp", C_FP, "white", 1.0), ("nocrowd", "none", C_FP, 1.6),
                                  ("conf", C_CONF, "white", 1.0), ("hit", C_HIT, "black", 1.0)):
            sel = inw_fm[cat == key]
            if len(sel):
                ax.scatter(sel.geometry.x, sel.geometry.y, s=52, marker="s",
                           facecolors=fc, edgecolors=edge, linewidths=lw, zorder=4)
                pick = sel
                if key == "fp":   # unambiguous example: interior of a majority-No cluster
                    tan = inw_fm[(cat == "fp") & (inw_f[mcol] == 0).values]
                    if len(tan) > 1:
                        xs, ys = tan.geometry.x.values, tan.geometry.y.values
                        nn = [(np.hypot(xs - a, ys - b) < 25).sum() for a, b in zip(xs, ys)]
                        pick = tan.iloc[[int(np.argmax(nn))]]
                    elif len(tan):
                        pick = tan
                mid = pick.iloc[(np.abs(pick.geometry.y - (y0 + y1) / 2)
                                 + np.abs(pick.geometry.x - (x0 + x1) / 2)).argsort()]
                examples[key] = mid.iloc[0].geometry
        for _, r in inw_c.iterrows():
            ax.add_patch(plt.Circle((r.geometry.x, r.geometry.y), R_MATCH, fc="none",
                                    ec="#333333", ls="--", lw=1.1, zorder=5))
        ax.scatter(inw_c.geometry.x, inw_c.geometry.y, s=140, marker="*", c="black",
                   zorder=6)
        if mcol == "m2":
            fl = polys[(polys.m1 == 1) != (polys.m2 == 1)]
            for _, r in fl.iterrows():
                ax.add_patch(plt.Polygon(np.asarray(r.geometry.exterior.coords), fc="none",
                                         ec=C_FLIP, lw=2.2, ls=(0, (4, 2)), zorder=7))
            ax.text(0.02, 0.975,
                    f"confirmation status flipped in {len(fl)} cells in view —\n"
                    "their flags move in or out of the adjusted numerator",
                    transform=ax.transAxes, fontsize=9, va="top", color="#222222",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=C_FLIP, alpha=.95),
                    zorder=9)
        else:
            notes = [("conf", "no expert point, but cell majority\n“Yes” → added to numerator",
                      (0.02, 0.975), "left", "top"),
                     ("fp", "cell majority “No” →\nstays a false positive",
                      (0.02, 0.10), "left", "bottom"),
                     ("hit", "expert point ≤10 m → true positive\n(crowd plays no role)",
                      (0.98, 0.975), "right", "top"),
                     ("nocrowd", "no crowd votes → outside sample\n(confirmed rate extrapolated here)",
                      (0.98, 0.10), "right", "bottom")]
            for key, txt, (tx, ty), ha, va in notes:
                if key in examples:
                    g = examples[key]
                    ax.annotate(txt, xy=(g.x, g.y), xytext=(tx, ty),
                                textcoords="axes fraction", fontsize=9, ha=ha, va=va,
                                color="#222222", zorder=9,
                                arrowprops=dict(arrowstyle="-", color="#555555", lw=.9,
                                                shrinkB=5),
                                bbox=dict(boxstyle="round,pad=0.3", fc="white",
                                          ec="#bbbbbb", alpha=.95))
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(ttl, fontsize=11.5, loc="left")
        ax.plot([x0 + 18, x0 + 118], [y0 + 16, y0 + 16], c="k", lw=3,
                solid_capstyle="butt", zorder=8)
        ax.text(x0 + 68, y0 + 24, "100 m", ha="center", fontsize=8.5, zorder=8)

    handles = [
        Line2D([], [], marker="s", ls="", ms=9, mfc=C_HIT, mec="black",
               label="flag matched by expert point ≤10 m → true positive"),
        Line2D([], [], marker="s", ls="", ms=9, mfc=C_CONF, mec="white",
               label="unmatched flag, cell majority “Yes” → crowd-confirmed (added to numerator)"),
        Line2D([], [], marker="s", ls="", ms=9, mfc=C_FP, mec="white",
               label="unmatched flag, cell majority “No”/“Not sure” → stays false positive"),
        Line2D([], [], marker="s", ls="", ms=9, mfc="white", mec=C_FP,
               label="unmatched flag, no crowd votes → outside sample, rate extrapolated\n"
                     "(none in this window — the crowd saw 98% of Microsoft's flags)"),
        Line2D([], [], marker="*", ls="", ms=13, mfc="black", mec="black",
               label="CEMS expert damage point (dashed = 10 m match radius)"),
        Patch(fc=T_YES, ec="#cccccc", label="cell majority “Yes”"),
        Patch(fc=T_NO, ec="#cccccc", label="cell majority “No damage”"),
        Patch(fc=T_UNSURE, ec="#cccccc", label="cell majority “Not sure”"),
        Line2D([], [], color=C_FLIP, lw=2.2, ls="--",
               label="confirmation status flipped between rounds"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8.6, frameon=False,
               bbox_to_anchor=(0.5, 0.035))
    fig.suptitle("How the MapSwipe crowd enters the precision calculation — "
                 "Microsoft flags, Catia La Mar strip", fontsize=13.5, x=0.5, y=0.985)
    fig.text(0.5, 0.005,
             f"Whole strip: {stats['strip_flags']:,} Microsoft flags in crowd-voted cells, "
             f"{stats['strip_hits']} expert-matched; of the {stats['unmatched']:,} unmatched, "
             f"the crowd confirms {stats['conf_r1']:.1%} (round 1) → {stats['conf_r2']:.1%} "
             f"(round 2). rq2i extrapolates this rate to un-voted flags.",
             ha="center", fontsize=9.5, style="italic")
    fig.tight_layout(rect=(0, 0.12, 1, 0.965))
    out = os.path.join(FIGS, "rq7_crowd_adjustment_explainer.png")
    fig.savefig(out, dpi=150)
    print("wrote", out)


if __name__ == "__main__":
    main()
