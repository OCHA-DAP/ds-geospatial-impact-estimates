"""Shared Overture base, POLYGON distance: singles and k-of-6 rules, core region, r = 10/20/30.

Third frame for the reviewer question. The paper's shared-base numbers (rq5b) measure from each
Overture building's centroid; the native run measures from each product's delivered geometry. This
keeps the fairness of one common base but measures from the Overture footprint polygon, so a CEMS
point sitting on a building matches it regardless of building size. Flags per building come from
gold building_flags (OSU pinned v0 by the lib helper), joined to Overture polygons by id.

Run: uv run --group etl --with matplotlib python exploratory/paper/artefacts/RQ0-matching-basis/native_rerun/shared_base_polygon.py
"""
from __future__ import annotations
import os, sys, warnings
warnings.filterwarnings("ignore")
import geopandas as gpd, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
import gie_paper as gp  # noqa: E402
from native_vs_centroid_core import core_region, match_rate, RADII, COL, RQ5, KEY  # noqa: E402

FLAGS = {"Microsoft": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg", "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}


def main():
    uh_all = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    core = core_region(uh_all)
    pts = gp.to_metric(gp.cems_points())
    cems = pts[pts.damage_class.isin([2, 3])]; cems = cems[cems.within(core)]
    assert len(cems) == 1467, len(cems)

    b = gpd.GeoSeries([core], crs=gp.METRIC_CRS).to_crs(4326).total_bounds
    ov = gp.to_metric(gp.overture_window(*b))
    ov = ov[ov.geometry.representative_point().within(core)]
    flags = gp.building_flags(columns=list(FLAGS.values()))
    bld = ov.merge(flags, on="id", how="inner")
    for c in FLAGS.values():
        bld[c] = bld[c].fillna(False).astype(bool).astype(int)
    bld["k"] = bld[list(FLAGS.values())].sum(axis=1)
    print(f"core Overture buildings with flags: {len(bld):,} (rq5b universe: 57,241)")

    rows = []
    rules = [(name, bld[bld[col] == 1]) for name, col in FLAGS.items()] + \
            [(f"{k}-of-6", bld[bld.k >= k]) for k in range(1, 7)]
    for r in RADII:
        ref = pd.read_csv(os.path.join(HERE, "..", "..", "RQ5-ensemble", RQ5[r])).set_index("rule")
        for name, sub in rules:
            tp_r, n_pts = match_rate(cems, sub, r)
            tp_p, n_f = match_rate(sub, cems, r)
            R, P = tp_r / n_pts, (tp_p / n_f if n_f else float("nan"))
            F1 = 2 * P * R / (P + R) if (P + R) else float("nan")
            key = KEY.get(name, name)
            c = ref.loc[key]
            rows.append(dict(rule=name, radius_m=r, flags=n_f, poly_P=round(P, 3), poly_R=round(R, 3), poly_F1=round(F1, 3),
                             centroid_flags=int(c["flagged"]), centroid_P=round(c["P_cems"], 3), centroid_R=round(c["R_cems"], 3), centroid_F1=round(c["F1_cems"], 3)))
            print(f"  r={r:>2} {name:10} poly n={n_f:6,} P={P:.3f} R={R:.3f} F1={F1:.3f} | centroid n={int(c['flagged']):6,} P={c['P_cems']:.3f} R={c['R_cems']:.3f} F1={c['F1_cems']:.3f}")
    df = pd.DataFrame(rows)
    out = os.path.join(HERE, "shared_base_polygon_core.csv"); df.to_csv(out, index=False); print("wrote", out)

    # figure: three frames at r=10 for singles (native from the sibling CSV) + voting rules in poly vs centroid
    nat = pd.read_csv(os.path.join(HERE, "native_vs_centroid_core.csv")); nat = nat[nat.radius_m == 10].set_index("product")
    d = df[df.radius_m == 10].set_index("rule")
    singles = list(COL); votes = [f"{k}-of-6" for k in range(1, 7)]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4), gridspec_kw={"width_ratios": [6, 6]})
    ax = axes[0]; x = range(len(singles)); w = 0.27
    ax.bar([i - w for i in x], [d.loc[s, "centroid_F1"] for s in singles], w, color="#9db1b3", label="shared base, centroid (paper)")
    ax.bar([i for i in x], [d.loc[s, "poly_F1"] for s in singles], w, color="#1862d8", label="shared base, polygon (this run)")
    ax.bar([i + w for i in x], [nat.loc[s, "native_F1"] for s in singles], w, color="#269777", label="delivered geometry (native)")
    ax.set_xticks(list(x)); ax.set_xticklabels(singles, fontsize=9); ax.set_title("Single products, F1 at r = 10 m", loc="left", fontsize=10)
    ax.legend(fontsize=8.5, frameon=False); ax.grid(axis="y", alpha=.25)
    ax = axes[1]; x = range(len(votes))
    ax.bar([i - w/2 for i in x], [d.loc[v, "centroid_F1"] for v in votes], w, color="#9db1b3", label="centroid (paper)")
    ax.bar([i + w/2 for i in x], [d.loc[v, "poly_F1"] for v in votes], w, color="#1862d8", label="polygon (this run)")
    best_nat = nat.native_F1.max(); ax.axhline(best_nat, color="#269777", ls="--", lw=1.2)
    ax.text(len(votes) - .5, best_nat, f" best native single {best_nat:.2f}", ha="right", va="bottom", fontsize=8, color="#269777")
    ax.set_xticks(list(x)); ax.set_xticklabels(votes, fontsize=9); ax.set_title("k-of-6 voting rules, F1 at r = 10 m", loc="left", fontsize=10)
    ax.legend(fontsize=8.5, frameon=False); ax.grid(axis="y", alpha=.25)
    for a in axes:
        for s in ("top", "right"): a.spines[s].set_visible(False)
    fig.suptitle("Three matching frames, same 1,467 CEMS points, same core region", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "fig_three_frames_r10.png"), dpi=140); print("wrote figure")


if __name__ == "__main__":
    main()
