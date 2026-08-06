"""RQ5d — is the agreement product just a byproduct of filtering (fewer flags)?

User's experiment (2026-07-27): agreement rules flag far fewer buildings; maybe ANY
thinning of the flag list would raise precision. Test with a random-removal null:
randomly drop flags from the union, recompute precision, repeat 100x, at a ladder of
retained fractions — then overlay the ACTUAL k-of-6 agreement rules on the same axes.

Statistics predict random thinning is precision-NEUTRAL (drops TP and FP in the same
proportion). If the k-of-6 points sit far above the flat random-null band, the ensemble
gain is SELECTION (agreement correlates with real damage), not filtering.

Precision = share of flagged buildings within 10 m of a CEMS {2,3} point. Core region
(rq5b), gold flags OSU v0-pinned.

Run: uv run --group etl --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ5-ensemble/scripts/rq5d_filtering_null.py
"""
from __future__ import annotations
import io, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
POS = (2, 3)
R = 10
NBOOT = 100
MEMBERS = ["ms_dmg", "sar_dmg", "osu_dmg", "uh_dmg", "list_dmg", "debris_dmg"]
# a fixed RNG stream without Math.random-style nondeterminism
RNG = np.random.default_rng(884)


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
    d = gp.building_flags(columns=["lon", "lat", *MEMBERS])
    bld = gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d.lon, d.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    region = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    for a in (gp.dissolve_union(gp.microsoft_aoi()), gp.dissolve_union(gp.impact_v2_aoi()),
              gp.dissolve_union(gp.osu_aoi()), uh_aoi(),
              gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                            "analysed_extent.parquet"))):
        region = region.intersection(a)
    inreg = bld.geometry.within(region).to_numpy()
    votes = np.zeros(len(d), int)
    for c in MEMBERS:
        votes += d[c].to_numpy(dtype="float64", na_value=0.0).astype(int)

    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    cems = cems[cems.geometry.within(region)]
    ct = cKDTree(np.c_[cems.geometry.x, cems.geometry.y])

    # is_tp per building = a CEMS damage point within R
    xy = np.c_[bld.geometry.x, bld.geometry.y]
    is_tp = (ct.query(xy, k=1)[0] <= R)

    union_mask = inreg & (votes >= 1)
    u_tp = is_tp[union_mask]
    n_union = int(union_mask.sum())
    p_union = u_tp.mean()
    print(f"union: {n_union:,} flags | precision {p_union:.3f}")

    # random-removal null: keep a fraction f of the union, N bootstrap draws
    fracs = [1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.10, 0.06, 0.03, 0.015, 0.006]
    rows = []
    for f in fracs:
        k = max(1, int(round(f * n_union)))
        means = [u_tp[RNG.choice(n_union, size=k, replace=False)].mean() for _ in range(NBOOT)]
        rows.append(dict(kind="random-thinned union", n_flags=k, frac=f,
                         precision=round(float(np.mean(means)), 4),
                         lo=round(float(np.percentile(means, 2.5)), 4),
                         hi=round(float(np.percentile(means, 97.5)), 4)))
    # actual k-of-6 agreement rules
    for kk in range(1, 7):
        m = inreg & (votes >= kk)
        if m.sum() == 0:
            continue
        rows.append(dict(kind=f"{kk}-of-6 agreement", n_flags=int(m.sum()), frac=np.nan,
                         precision=round(float(is_tp[m].mean()), 4), lo=np.nan, hi=np.nan))
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq5d_filtering_null.csv"), index=False)
    print(out.to_string(index=False))

    # figure
    rnd = out[out.kind == "random-thinned union"].sort_values("n_flags")
    ag = out[out.kind.str.contains("agreement")].sort_values("n_flags")
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.fill_between(rnd.n_flags, rnd.lo, rnd.hi, color="#c9ced4", alpha=0.6,
                    label="random thinning of the union (95% band, 100 draws)")
    ax.plot(rnd.n_flags, rnd.precision, "o-", color="#6b7684", lw=2, ms=6)
    ax.plot(ag.n_flags, ag.precision, "s-", color="#2a78d6", lw=2, ms=13, zorder=5,
            label="actual k-of-6 agreement rules")
    for _, r in ag.iterrows():
        ax.annotate(r.kind.split("-")[0], (r.n_flags, r.precision), ha="center",
                    va="center", fontsize=9, color="white", zorder=6, weight="bold")
    ax.set_xscale("log")
    ax.set_xlabel("number of flagged buildings kept (log scale; ← fewer)", fontsize=12)
    ax.set_ylabel("precision (share of flags on real CEMS damage, r = 10 m)", fontsize=12)
    ax.invert_xaxis()
    ax.tick_params(labelsize=11)
    ax.legend(fontsize=11, loc="upper left")
    ax.set_title("The agreement gain is SELECTION, not filtering\n"
                 "Random removal keeps precision flat; agreement lifts it far above "
                 "any random thinning to the same size", fontsize=12.5)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq5d_filtering_null.png"), dpi=150)
    print("wrote rq5d_filtering_null.png")


if __name__ == "__main__":
    main()
