"""RQ3d — LISA (Local Moran's I): a spatially-varying reliability surface per product.

RQ3b/RQ3c showed error structure varies BETWEEN named areas. Here: per res-8 cell, Local
Moran's I on the exposure-adjusted GLM residuals classifies each cell as
  HH  in a local clump of OVER-flagging  -> local systematic false-positive zone
  LL  in a local clump of UNDER-flagging -> local blind spot
  HL/LH outliers
  ns  locally random error               -> trustworthy-noise territory
(significance: 999 permutations per cell, p<0.05 uncorrected — the standard LISA caveat;
interpret clusters, not single cells). Region per product = CEMS latest extent ∩ its AOI;
UNEP under the stated coverage assumption (core region only).

Run: uv run --group etl --with statsmodels --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3d_lisa_reliability.py
"""
from __future__ import annotations
import io, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
import statsmodels.api as sm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
POS = (2, 3)
RES = 8
RNG = np.random.default_rng(884)
N_PERM = 999
FLAGS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
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


def lisa(cells, values):
    """Local Moran's I with per-cell permutation p (values permuted among OTHER cells)."""
    idx = {c: i for i, c in enumerate(cells)}
    nbr = [[idx[n] for n in h3.grid_disk(c, 1) if n != c and n in idx] for c in cells]
    z = (values - values.mean()) / (values.std() + 1e-12)
    lag = np.array([z[nb].mean() if nb else np.nan for nb in nbr])
    Ii = z * lag
    # conditional permutation: for each cell, how extreme is its lag under random neighbours
    p = np.full(len(cells), np.nan)
    pool = z.copy()
    for i, nb in enumerate(nbr):
        if not nb:
            continue
        k = len(nb)
        others = np.delete(pool, i)
        sims = np.array([others[RNG.integers(0, len(others), k)].mean() for _ in range(N_PERM)])
        sim_I = z[i] * sims
        p[i] = (np.sum(np.abs(sim_I) >= abs(Ii[i])) + 1) / (N_PERM + 1)
    cls = np.full(len(cells), "ns", dtype=object)
    sig = (p < 0.05)
    cls[sig & (z > 0) & (lag > 0)] = "HH"
    cls[sig & (z < 0) & (lag < 0)] = "LL"
    cls[sig & (z > 0) & (lag < 0)] = "HL"
    cls[sig & (z < 0) & (lag > 0)] = "LH"
    return cls


def main():
    import ocha_stratus as stratus
    df = gp.building_flags(columns=["lon", "lat", *FLAGS.values()])  # OSU pinned to v0 (paper basis)
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    ext_latest = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    aois = {"MS": gp.dissolve_union(gp.microsoft_aoi()),
            "IMPACT": gp.dissolve_union(gp.impact_v2_aoi()),
            "OSU": gp.dissolve_union(gp.osu_aoi()),
            "UH": uh_aoi(),
            "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                                  "analysed_extent.parquet"))}
    core = ext_latest
    for a in aois.values():
        core = core.intersection(a)
    aois["UNEP"] = core  # stated coverage assumption

    ll_all = bld.to_crs(4326)
    bld["cell"] = [h3.latlng_to_cell(p.y, p.x, RES) for p in ll_all.geometry]
    cems_ll = cems.to_crs(4326)
    cems = cems.assign(cell=[h3.latlng_to_cell(p.y, p.x, RES) for p in cems_ll.geometry])

    fig, axes = plt.subplots(2, 3, figsize=(16, 7))
    out = []
    COLORS = {"HH": "#c62828", "LL": "#1565c0", "HL": "#ef9a9a", "LH": "#90caf9", "ns": "#d5d5d5"}
    for ax, (nm, col) in zip(axes.flat, FLAGS.items()):
        region = ext_latest.intersection(aois[nm])
        bm = bld.geometry.within(region)
        d = (bld[bm].groupby("cell")
             .agg(base=("cell", "size"), pdmg=(col, "sum"))
             .join(cems[cems.geometry.within(region)].groupby("cell").size().rename("cems"))
             .fillna(0))
        d = d[d.base >= 1]
        X = sm.add_constant(np.log1p(d.cems.to_numpy()))
        fit = sm.GLM(d.pdmg.to_numpy(), X, family=sm.families.Poisson(),
                     offset=np.log(d.base.to_numpy())).fit()
        resid = np.asarray(fit.resid_pearson)
        cls = lisa(d.index.tolist(), resid)
        d["lisa"] = cls
        counts = pd.Series(cls).value_counts().to_dict()
        out.append(dict(product=nm, cells=len(d), **{k: counts.get(k, 0) for k in COLORS}))
        print(out[-1], flush=True)
        ll = np.array([h3.cell_to_latlng(c) for c in d.index])
        for k in ("ns", "LH", "HL", "LL", "HH"):
            m = cls == k
            if m.any():
                ax.scatter(ll[m, 1], ll[m, 0], c=COLORS[k], s=14, label=k if k != "ns" else None)
        ax.set_title(f"{nm}", fontsize=10)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        d.reset_index(names="h3").assign(product=nm).to_csv(
            os.path.join(HERE, "..", f"rq3d_lisa_{nm.lower()}.csv"), index=False)
    h = [plt.Line2D([], [], marker="o", ls="", c=COLORS[k],
                    label={"HH": "HH — local over-flagging clump (distrust flags here)",
                           "LL": "LL — local blind spot (distrust silence here)",
                           "HL": "HL outlier", "LH": "LH outlier"}[k])
         for k in ("HH", "LL", "HL", "LH")]
    fig.legend(handles=h, loc="lower center", ncol=4, fontsize=8, frameon=False)
    fig.suptitle("RQ3d — LISA reliability surfaces: where each product's error is locally "
                 "systematic (colour) vs locally random (grey = trustworthy noise)", fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(os.path.join(FIGS, "rq3d_lisa_reliability.png"), dpi=130)
    pd.DataFrame(out).to_csv(os.path.join(HERE, "..", "rq3d_lisa_summary.csv"), index=False)
    print("wrote rq3d_lisa_summary.csv + per-product cell CSVs + figs/rq3d_lisa_reliability.png")


if __name__ == "__main__":
    main()
