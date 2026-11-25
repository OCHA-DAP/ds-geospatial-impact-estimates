"""Native-geometry vs shared-base (centroid) scoring for all six products, core region.

Non-destructive candidate analysis prompted by review (2026-09-10): the brief's tbl-frames claims
the two matching implementations agree to within 0.005, but no six-product native run existed.
This scores each product's DELIVERED geometry (dual-anchored, RQ0 design) against the same 1,467
CEMS damaged/destroyed points inside the same 60.8 km2 core region used by rq5b, at r = 10/20/30 m,
and sets the numbers beside rq5b's shared-base (centroid) values. Nothing frozen is overwritten.

Run: uv run --group etl python exploratory/paper/artefacts/RQ0-matching-basis/native_rerun/native_vs_centroid_core.py
"""
from __future__ import annotations
import os, sys, warnings
warnings.filterwarnings("ignore")
import geopandas as gpd, pandas as pd, h3
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

RADII = (10, 20, 30)
COL = {"Microsoft": "#2a78d6", "IMPACT": "#8a5cd6", "OSU": "#1b9e77", "UH": "#e6a817", "LIST": "#d95f02", "UNEP": "#c65d9e"}
RQ5 = {10: "rq5b_six_member.csv", 20: "rq5b_six_member_r20.csv", 30: "rq5b_six_member_r30.csv"}
KEY = {"Microsoft": "MS", "IMPACT": "IMPACT", "OSU": "OSU", "UH": "UH", "LIST": "LIST", "UNEP": "UNEP"}


def match_rate(left, right, r):
    if len(left) == 0 or len(right) == 0:
        return 0, len(left)
    l = left.reset_index(drop=True).reset_index(names="_lid")
    m = gpd.sjoin_nearest(l[["_lid", "geometry"]], right[["geometry"]], max_distance=r, how="inner", distance_col="_d")
    return m["_lid"].nunique(), len(l)


def core_region(uh):
    cells = {h3.latlng_to_cell(p.y, p.x, 9) for p in uh.geometry.representative_point()}
    dil = set()
    for c in cells:
        dil.update(h3.grid_disk(c, 1))
    uh_aoi = gp.dissolve_union(gpd.GeoDataFrame(geometry=[unary_union(
        [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in dil])], crs=4326))
    aois = [gp.dissolve_union(gp.microsoft_aoi()), gp.dissolve_union(gp.impact_v2_aoi()),
            gp.dissolve_union(gp.osu_aoi()), uh_aoi,
            gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE", "analysed_extent.parquet"))]
    cems = gp.to_metric(gp.cems_extent().query("is_latest"))
    core = cems.geometry.make_valid().union_all()
    for a in aois:
        core = core.intersection(a)
    return core


def main():
    uh_all = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    core = core_region(uh_all)
    print(f"core region: {core.area/1e6:.1f} km2")
    pts = gp.to_metric(gp.cems_points())
    cems = pts[pts.damage_class.isin([2, 3])]
    cems = cems[cems.within(core)]
    assert len(cems) == 1467, f"expected 1,467 CEMS points in core, got {len(cems)}"

    b = gpd.GeoSeries([core], crs=gp.METRIC_CRS).to_crs(4326).total_bounds
    ov = gp.overture_window(*b)
    import io, ocha_stratus as stratus
    list_ids = set(pd.read_parquet(io.BytesIO(stratus.load_blob_data(
        gp.S.blob_path("silver", "source=list", "adm0=VE", "building_damage.parquet", event=None),
        stage="dev", container_name=gp.S.container)), columns=["id"]).id)
    unep = gp.unep()
    prods = {
        "Microsoft": gp.microsoft(),
        "IMPACT": gp.impact_v2(),
        "OSU": gp.osu(),
        "UH": uh_all[uh_all.cls.isin([2, 3])],
        "LIST": ov[ov["id"].isin(list_ids)],
        "UNEP": unep[unep.debris_tonnes > 0] if "debris_tonnes" in unep.columns else unep,
    }
    rows = []
    for name, g in prods.items():
        gm = gp.to_metric(g)
        foot = gm[gm.geometry.representative_point().within(core)]
        for r in RADII:
            tp_r, n_pts = match_rate(cems, foot, r)
            tp_p, n_f = match_rate(foot, cems, r)
            R, P = tp_r / n_pts, (tp_p / n_f if n_f else float("nan"))
            F1 = 2 * P * R / (P + R) if (P + R) else float("nan")
            c = pd.read_csv(os.path.join(HERE, "..", "..", "RQ5-ensemble", RQ5[r])).set_index("rule").loc[KEY[name]]
            rows.append(dict(product=name, radius_m=r, native_flags=n_f, native_P=round(P, 3), native_R=round(R, 3), native_F1=round(F1, 3),
                             centroid_flags=int(c["flagged"]), centroid_P=round(c["P_cems"], 3), centroid_R=round(c["R_cems"], 3), centroid_F1=round(c["F1_cems"], 3)))
            print(f"  {name:10} r={r:>2}  native  n={n_f:6,} P={P:.3f} R={R:.3f} F1={F1:.3f}   |   centroid n={int(c['flagged']):6,} P={c['P_cems']:.3f} R={c['R_cems']:.3f} F1={c['F1_cems']:.3f}")
    df = pd.DataFrame(rows)
    for m in ("P", "R", "F1"):
        df[f"d{m}"] = (df[f"native_{m}"] - df[f"centroid_{m}"]).round(3)
    out = os.path.join(HERE, "native_vs_centroid_core.csv"); df.to_csv(out, index=False); print("wrote", out)

    # figure 1: dumbbells at r=10 for P and R
    d10 = df[df.radius_m == 10].set_index("product").loc[list(COL)]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    for ax, m, lab in zip(axes, ("P", "R", "F1"), ("precision", "recall", "F1")):
        for i, (p, row) in enumerate(d10.iterrows()):
            ax.plot([row[f"centroid_{m}"], row[f"native_{m}"]], [i, i], color=COL[p], lw=2.5, zorder=1)
            ax.scatter(row[f"centroid_{m}"], i, s=70, facecolors="white", edgecolors=COL[p], lw=2, zorder=2)
            ax.scatter(row[f"native_{m}"], i, s=70, color=COL[p], zorder=3)
            ax.annotate(f"{row[f'centroid_{m}']:.3f}→{row[f'native_{m}']:.3f}", (max(row[f"centroid_{m}"], row[f"native_{m}"]), i), xytext=(8, -3), textcoords="offset points", fontsize=8.5, color="#333")
        ax.set_yticks(range(len(d10))); ax.set_yticklabels(d10.index); ax.invert_yaxis()
        ax.set_title(f"{lab}, r = 10 m (core region)", fontsize=10, loc="left")
        ax.grid(axis="x", alpha=.25); ax.set_xlim(left=0)
        for s in ("top", "right"): ax.spines[s].set_visible(False)
    axes[0].scatter([], [], facecolors="white", edgecolors="k", label="shared base (centroid), rq5b")
    axes[0].scatter([], [], color="k", label="native geometry (this run)")
    axes[0].legend(loc="lower right", fontsize=8.5, frameon=False)
    fig.suptitle("Same 1,467 CEMS points, same 60.8 km² core: delivered geometry vs shared-base scoring", fontsize=11, x=0.01, ha="left")
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "fig_native_vs_centroid_r10.png"), dpi=140)

    # figure 2: does the ordering change? F1 at each radius, both frames, with the combination rules for context
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    for ax, r in zip(axes, RADII):
        d = df[df.radius_m == r].set_index("product").loc[list(COL)]
        x = range(len(d))
        ax.bar([i - 0.2 for i in x], d.centroid_F1, width=0.38, color=[COL[p] for p in d.index], alpha=.45, label="shared base")
        ax.bar([i + 0.2 for i in x], d.native_F1, width=0.38, color=[COL[p] for p in d.index], label="native")
        v = pd.read_csv(os.path.join(HERE, "..", "..", "RQ5-ensemble", RQ5[r])).set_index("rule")
        best_vote = v.loc[[f"{k}-of-6" for k in range(1, 7)], "F1_cems"].max()
        ax.axhline(best_vote, color="#1862d8", ls="--", lw=1.2); ax.text(len(d) - .5, best_vote, f" best voting rule {best_vote:.2f}", va="bottom", ha="right", fontsize=8, color="#1862d8")
        ax.set_xticks(list(x)); ax.set_xticklabels(d.index, rotation=0, fontsize=8.5)
        ax.set_title(f"F1 at r = {r} m", fontsize=10, loc="left"); ax.grid(axis="y", alpha=.25)
        for s in ("top", "right"): ax.spines[s].set_visible(False)
    axes[0].legend(fontsize=8.5, frameon=False, loc="upper left")
    fig.suptitle("Single-product F1 in both frames; blue line = best k-of-6 voting rule (shared base) at that radius", fontsize=11, x=0.01, ha="left")
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "fig_f1_both_frames.png"), dpi=140)
    print("wrote figures")


if __name__ == "__main__":
    main()
