"""RQ5 — consensus ensemble: does k-of-n voting improve the building-level damage MAP?

See ../DESIGN.md. Construction on the gold Overture base (building_flags per-source flags);
scoring via the RQ2 dual-anchor harness vs native CEMS builtUpP points, r=10 m primary /
{5,20} sensitivity, within `CEMS latest extent ∩ member AOIs` per rule. Each voting rule is a
synthetic product. Members: MS, IMPACT v2, OSU, UH. UH AOI derived (H3 res-9 cells k=1 dilated
containing >=1 UH footprint of any grade — intact included, so "where it looked" is defined).

Outputs: rq5_summary.csv (all rules x radii + region areas), figs/rq5_pr_frontier_r10.png,
figs/rq5_consensus_gaps.png (all-member consensus buildings with no CEMS point within 20 m).

Run: uv run --group etl --with matplotlib --with scipy python \
       exploratory/paper/artefacts/RQ5-ensemble/scripts/rq5_ensemble.py
"""
from __future__ import annotations
import io, os, sys
from itertools import combinations
import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import h3
from shapely.geometry import Polygon
from shapely.ops import unary_union

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

FIGS = os.path.join(os.path.dirname(__file__), "..", "figs")
os.makedirs(FIGS, exist_ok=True)
POS = (2, 3)
RADII = (10, 5, 20)
MEMBERS = ("ms", "impact", "osu", "uh")
GAP_R = 20  # consensus-gap: no CEMS point within this many metres


def building_flags():
    import ocha_stratus as stratus
    df = gp.building_flags(columns=["id", "lon", "lat", "ms_dmg", "sar_dmg", "osu_dmg", "uh_dmg"])  # OSU pinned to v0 (paper basis)
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    return g.to_crs(gp.METRIC_CRS).rename(
        columns={"ms_dmg": "dmg_ms", "sar_dmg": "dmg_impact", "osu_dmg": "dmg_osu",
                 "uh_dmg": "dmg_uh"})


def uh_aoi():
    """Derived UH analysed extent: H3 res-9 cells (k=1 dilated) with >=1 UH footprint, any grade."""
    g = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    pts = g.geometry.representative_point()
    cells = {h3.latlng_to_cell(p.y, p.x, 9) for p in pts}
    dilated = set()
    for c in cells:
        dilated.update(h3.grid_disk(c, 1))
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in dilated]
    aoi = gpd.GeoDataFrame(geometry=[unary_union(polys)], crs=4326)
    return gp.dissolve_union(aoi)


def rate(left_pts, right_pts, r):
    n, d = gp.match_rate(left_pts, right_pts, r)
    return n / d if d else np.nan


def main():
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)][["geometry"]]
    ext = gp.cems_extent()
    ext_latest = gp.to_metric(ext[ext.is_latest == True]).geometry.make_valid().union_all()  # noqa: E712
    bld = building_flags()
    aois = {
        "ms": gp.dissolve_union(gp.microsoft_aoi()),
        "impact": gp.dissolve_union(gp.impact_v2_aoi()),
        "osu": gp.dissolve_union(gp.osu_aoi()),
        "uh": uh_aoi(),
    }
    print("inputs: buildings", len(bld), "| cems pts", len(cems))

    # per-building AOI membership (point-in-poly per member, computed once)
    for m, a in aois.items():
        bld[f"in_{m}"] = bld.geometry.within(a)
        print(f"  {m}: {bld[f'in_{m}'].sum():,} buildings in AOI")
    bld["in_cems"] = bld.geometry.within(ext_latest)

    # rules: (name, members, flag-predicate over the member dmg columns)
    rules = [(m.upper(), (m,), lambda d, m=m: d[f"dmg_{m}"] == 1) for m in MEMBERS]
    for a, b in combinations(MEMBERS, 2):
        pred_ab = lambda d, a=a, b=b: (d[f"dmg_{a}"] == 1) & (d[f"dmg_{b}"] == 1)  # noqa: E731
        rules.append((f"{a.upper()}∧{b.upper()}", (a, b), pred_ab))
        # same pair restricted to the quad region -> identical universe for H1 pair-type compare
        rules.append((f"{a.upper()}∧{b.upper()} (quad)", MEMBERS, pred_ab))
    votes = bld[[f"dmg_{m}" for m in MEMBERS]].sum(axis=1)
    for k in (1, 2, 3, 4):
        rules.append((f"{k}-of-4", MEMBERS, lambda d, k=k: votes.loc[d.index] >= k))

    rows = []
    for name, members, pred in rules:
        region_mask = bld["in_cems"]
        reg_geom = ext_latest
        for m in members:
            region_mask &= bld[f"in_{m}"]
            reg_geom = reg_geom.intersection(aois[m])
        uni = bld[region_mask]
        flagged = uni[pred(uni)]
        cems_in = cems[cems.geometry.within(reg_geom)]
        row = dict(rule=name, members="+".join(members), n_bldg=len(uni),
                   n_flagged=len(flagged), n_cems=len(cems_in),
                   region_km2=round(reg_geom.area / 1e6, 1),
                   overdet=round(len(flagged) / max(len(cems_in), 1), 1))
        for r in RADII:
            rec = rate(cems_in, flagged, r)
            prec = rate(flagged, cems_in, r)
            f1 = 2 * prec * rec / (prec + rec) if (prec or 0) + (rec or 0) > 0 else 0.0
            row.update({f"recall_r{r}": round(rec, 3), f"precision_r{r}": round(prec, 3),
                        f"f1_r{r}": round(f1, 3)})
        rows.append(row)
        print(f"{name:14s} n={len(uni):7,} flag={len(flagged):6,} cems={len(cems_in):5,} "
              f"km2={row['region_km2']:7.1f}  P={row['precision_r10']:.3f} "
              f"R={row['recall_r10']:.3f} F1={row['f1_r10']:.3f}")

    out = pd.DataFrame(rows)
    csv = os.path.join(os.path.dirname(__file__), "..", "rq5_summary.csv")
    out.to_csv(csv, index=False)
    print("wrote", csv)

    # frontier fig (quad-region rules only: singles + k-of-4 share the same universe)
    on_quad = out[out.members == "+".join(MEMBERS)]
    quad = on_quad[~on_quad.rule.str.contains("quad")]
    pairs_q = on_quad[on_quad.rule.str.contains("quad")]
    singles = out[out.rule.isin([m.upper() for m in MEMBERS])]
    fig, ax = plt.subplots(figsize=(7.5, 6))
    for f1 in (0.1, 0.2, 0.3, 0.4, 0.6):  # iso-F1 curves
        r = np.linspace(0.02, 1, 200)
        p = f1 * r / np.maximum(2 * r - f1, 1e-9)
        ok = (p > 0) & (p <= 1) & (2 * r > f1)
        ax.plot(r[ok], p[ok], ls=":", c="grey", lw=0.8)
        if ok.any():
            ax.annotate(f"F1={f1}", (r[ok][-1], p[ok][-1]), fontsize=7, color="grey")
    ax.scatter(singles["recall_r10"], singles["precision_r10"], c="tab:blue", label="singles")
    ax.scatter(pairs_q["recall_r10"], pairs_q["precision_r10"], c="tab:orange", marker="s",
               label="pairwise ∧ (quad region)")
    ax.scatter(quad["recall_r10"], quad["precision_r10"], c="tab:red", marker="D", label="k-of-4")
    for _, r_ in pd.concat([singles, pairs_q, quad]).iterrows():
        ax.annotate(r_["rule"].replace(" (quad)", ""), (r_["recall_r10"], r_["precision_r10"]),
                    textcoords="offset points", xytext=(5, 4), fontsize=8)
    ax.set_xlabel("recall (CEMS {2,3} points, r=10 m)")
    ax.set_ylabel("precision (flagged buildings, r=10 m)")
    ax.set_title("RQ5 — voting-rule frontier, quad-overlap region (singles re-baselined)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq5_pr_frontier_r10.png"), dpi=130)
    print("wrote figs/rq5_pr_frontier_r10.png")

    # consensus-as-CEMS-gaps: 4-of-4 flags with no CEMS point within GAP_R, quad region
    region_mask = bld["in_cems"]
    for m in MEMBERS:
        region_mask &= bld[f"in_{m}"]
    uni = bld[region_mask]
    cons = uni[votes.loc[uni.index] >= 4]
    if len(cons):
        j = gpd.sjoin_nearest(cons[["geometry"]], cems[["geometry"]],
                              max_distance=GAP_R, how="left", distance_col="_d")
        j = j[~j.index.duplicated()]
        gaps = cons.loc[j[j["_d"].isna()].index]
        ll = gaps.to_crs(4326)
        near = cons.loc[j[j["_d"].notna()].index].to_crs(4326)
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.scatter(near.geometry.x, near.geometry.y, s=6, c="tab:green",
                   label=f"consensus, CEMS-corroborated (n={len(near):,})")
        ax.scatter(ll.geometry.x, ll.geometry.y, s=6, c="tab:red",
                   label=f"consensus, NO CEMS point ≤{GAP_R} m (n={len(gaps):,})")
        ax.set_aspect("equal")
        ax.legend()
        ax.set_title("RQ5 — 4-of-4 consensus buildings vs CEMS corroboration (quad region)")
        fig.tight_layout()
        fig.savefig(os.path.join(FIGS, "rq5_consensus_gaps.png"), dpi=130)
        print(f"consensus 4-of-4: {len(cons):,} | candidate CEMS gaps: {len(gaps):,} "
              f"({len(gaps) / len(cons):.0%})")
        print("wrote figs/rq5_consensus_gaps.png")
    else:
        print("no 4-of-4 consensus buildings in quad region")


if __name__ == "__main__":
    main()
