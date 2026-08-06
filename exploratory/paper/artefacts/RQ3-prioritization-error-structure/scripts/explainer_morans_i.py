"""Visual explainer: first-order vs second-order effects, and what our Moran's I permutation
test actually does. Two figures:

  fig 1 (toy): the same irregular footprint filled with (a) spatially random values and
    (b) clustered values. Both look "clustered" against the full coordinate space — the
    footprint itself is a first-order effect. The clustering question is only about the
    ARRANGEMENT of values GIVEN the footprint.
  fig 2 (real, Microsoft Caraballeda res-8): observed exposure-GLM residuals on the real cell
    lattice vs one random permutation of the SAME values on the SAME lattice (= one draw from
    the null), plus the permutation distribution of I with the observed value marked.

Run: uv run --group etl --with statsmodels --with matplotlib --with scipy python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/explainer_morans_i.py
"""
from __future__ import annotations
import io, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import h3
import statsmodels.api as sm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

FIGS = os.path.join(os.path.dirname(__file__), "..", "figs")
RNG = np.random.default_rng(884)


# ---------- fig 1: toy — the footprint is not the clustering ----------
def toy():
    # irregular "footprint": union of a few blobs (like a coastal strip + barrios)
    pts = []
    for cx, cy, n, s in [(0, 0, 300, .8), (2.4, .4, 200, .5), (4.2, -.2, 250, .7), (6.2, .3, 150, .4)]:
        pts.append(RNG.normal([cx, cy], s, size=(n, 2)))
    xy = np.vstack(pts)
    d = ((xy[:, 0] - 3) ** 2 / 4 + xy[:, 1] ** 2)  # gradient used for the clustered panel
    v_rand = RNG.normal(size=len(xy))
    v_clus = -d + RNG.normal(scale=.6, size=len(xy))  # values follow a smooth spatial field
    fig, ax = plt.subplots(1, 2, figsize=(12, 3.4))
    for a, v, t in [(ax[0], v_rand, "(a) values RANDOM given the footprint — Moran's I ≈ 0"),
                    (ax[1], v_clus, "(b) values CLUSTERED given the footprint — Moran's I ≫ 0")]:
        a.scatter(xy[:, 0], xy[:, 1], c=v, cmap="RdBu_r", s=14)
        a.set_title(t, fontsize=10)
        a.set_aspect("equal"); a.set_xticks([]); a.set_yticks([])
    fig.suptitle("The footprint SHAPE is identical (a first-order effect, conditioned out); "
                 "the test only asks how values are arranged on it", fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "explainer_first_vs_second_order.png"), dpi=130)
    print("wrote figs/explainer_first_vs_second_order.png")


# ---------- fig 2: the real test, visualized (Microsoft, res 8) ----------
def real():
    import ocha_stratus as stratus
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin((2, 3))]
    ext = gp.cems_extent()
    ext_latest = gp.to_metric(ext[ext.is_latest == True]).geometry.make_valid().union_all()  # noqa: E712
    ms = gp.to_metric(gp.microsoft())
    aoi = gp.dissolve_union(gp.microsoft_aoi())
    region = ext_latest.intersection(aoi)

    b = stratus.load_blob_data(
        gp.S.blob_path("gold", "model=common", "adm0=VE", "building_flags.parquet"),
        stage="dev", container_name=gp.S.container)
    df = pd.read_parquet(io.BytesIO(b), columns=["lon", "lat"])
    base = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                            crs=4326).to_crs(gp.METRIC_CRS)

    def counts(g, nm):
        sub = g[g.geometry.representative_point().within(region)]
        ll = sub.to_crs(4326).geometry.representative_point()
        return pd.Series([h3.latlng_to_cell(p.y, p.x, 8) for p in ll]).value_counts().rename(nm)

    d = pd.concat([counts(base, "base"), counts(cems, "cems"), counts(ms, "pdmg")], axis=1).fillna(0)
    d = d[d.base >= 1]
    X = sm.add_constant(np.log1p(d.cems.to_numpy()))
    fit = sm.GLM(d.pdmg.to_numpy(), X, family=sm.families.Poisson(),
                 offset=np.log(d.base.to_numpy())).fit()
    resid = np.asarray(fit.resid_pearson)

    cells = d.index.tolist()
    idx = {c: i for i, c in enumerate(cells)}
    nbr = [[idx[n] for n in h3.grid_disk(c, 1) if n != c and n in idx] for c in cells]

    def moran(v):
        z = v - v.mean()
        lag = np.array([z[nb].mean() if nb else 0.0 for nb in nbr])
        keep = np.array([len(nb) > 0 for nb in nbr])
        return (z[keep] * lag[keep]).sum() / (z[keep] ** 2).sum()

    obs = moran(resid)
    perms = []
    v = resid.copy()
    for _ in range(999):
        RNG.shuffle(v)
        perms.append(moran(v))
    perms = np.array(perms)
    one_perm = resid.copy(); RNG.shuffle(one_perm)

    ll = np.array([h3.cell_to_latlng(c) for c in cells])
    lim = np.percentile(np.abs(resid), 98)
    fig, ax = plt.subplots(1, 3, figsize=(15, 3.8),
                           gridspec_kw={"width_ratios": [2, 2, 1.2]})
    for a, vals, t in [(ax[0], resid, f"OBSERVED residuals — I = {obs:.2f}"),
                       (ax[1], one_perm, f"SAME values, randomly shuffled on the SAME lattice — I = {moran(one_perm):.2f}")]:
        a.scatter(ll[:, 1], ll[:, 0], c=vals, cmap="RdBu_r", vmin=-lim, vmax=lim, s=30)
        a.set_title(t, fontsize=10); a.set_aspect("equal"); a.set_xticks([]); a.set_yticks([])
    ax[2].hist(perms, bins=40, color="lightgrey")
    ax[2].axvline(obs, color="crimson", lw=2)
    ax[2].set_title("999 shuffles: I under the null\nred = observed → p ≈ 0.001", fontsize=10)
    fig.suptitle("Our permutation test (Microsoft, Caraballeda res-8): the lattice — the 'footprint "
                 "shape' — is identical in every panel; only the value arrangement differs", fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "explainer_permutation_test.png"), dpi=130)
    print(f"wrote figs/explainer_permutation_test.png  (obs I={obs:.3f}, "
          f"null mean={perms.mean():.3f}±{perms.std():.3f})")


if __name__ == "__main__":
    toy()
    real()
