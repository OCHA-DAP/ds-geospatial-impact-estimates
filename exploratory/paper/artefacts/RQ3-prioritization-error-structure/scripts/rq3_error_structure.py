"""RQ3b — error structure: is over-detection NOISE (rank-preserving) or BIAS (rank-corrupting)?

Replaces the flawed `bias_rho` (mechanically confounded — CEMS in the ratio denominator).
The proper test, per RQ3 NOTES:

  1. Fit Poisson GLM  product_count ~ 1 + log1p(cems_count)  per H3 cell in the STRICT shared
     region (CEMS latest extent ∩ product AOI). Cell universe = every cell with >=1 base
     (Overture) building — zero-damage cells included; excluding them (as the rank test does)
     would hide FP structure in undamaged areas.
  2. Pearson residuals = over/under-detection NOT explained by true (CEMS) damage.
  3. (a) Spatial autocorrelation: Moran's I on residuals (H3 k=1 adjacency, row-standardised,
     999 permutations). Clumped residuals = spatially structured error.
     (b) Covariate regression: residuals ~ z(log building density) + z(dist-to-coast) + z(MMI),
     OLS with HC1 SEs. Error that follows non-damage covariates = the bias signature that
     would corrupt prioritization; error that follows none = noise.

Dataset basis (RQ0): silver CEMS points/extents + product silvers (native, no Overture snap).
The gold building_flags parquet is used ONLY for the base-building stock (id/lon/lat = the
Overture base universe; no damage labels read) — density covariate + cell universe.
MMI: max over the two USGS events (us6000t7zp M7.5 mainshock, us6000t7zc M7.2) of the
nearest ShakeMap contour value at the cell centre (error <= half contour interval).
Dist-to-coast: cell centre to dissolved CODAB adm0 boundary (nearest national boundary; for
these coastal AOIs that is the Caribbean coast).

Run: uv run --group etl --with statsmodels python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3_error_structure.py
"""
from __future__ import annotations
import io, json, os, sys
import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
import h3
import statsmodels.api as sm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

FIGS = os.path.join(os.path.dirname(__file__), "..", "figs")
os.makedirs(FIGS, exist_ok=True)
POS = (2, 3)  # headline CEMS positive classes (Damaged, Destroyed)
RNG = np.random.default_rng(884)  # EMSR884
N_PERM = 999
USGS_EVENTS = ("us6000t7zp", "us6000t7zc")


# --- covariate inputs (loaded once) ---------------------------------------------
def base_buildings():
    """Overture base stock as metric points (id/lon/lat only — no damage labels)."""
    import ocha_stratus as stratus
    b = stratus.load_blob_data(
        gp.S.blob_path("gold", "model=common", "adm0=VE", "building_flags.parquet"),
        stage="dev", container_name=gp.S.container)
    df = pd.read_parquet(io.BytesIO(b), columns=["id", "lon", "lat"])
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    return g.to_crs(gp.METRIC_CRS)


def mmi_contours():
    """All ShakeMap MMI contour lines (metric), column `value`, both events."""
    import ocha_stratus as stratus
    frames = []
    for ev in USGS_EVENTS:
        d = json.loads(stratus.load_blob_data(
            gp.S.blob_path("bronze", "source=usgs", "adm0=VE", f"event={ev}", "cont_mi.json"),
            stage="dev", container_name=gp.S.container))
        g = gpd.GeoDataFrame.from_features(d["features"], crs=4326)
        g["event"] = ev
        frames.append(g[["value", "event", "geometry"]])
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326).to_crs(gp.METRIC_CRS)


def coast_boundary():
    """Dissolved adm0 boundary (metric) — nearest-national-boundary = coast for these AOIs."""
    adm0 = gp.codab(0)
    return gp.to_metric(adm0).geometry.make_valid().union_all().boundary


def cell_covariates(cells, res, contours, coast):
    """DataFrame per cell: centre point, mmi (max over events, nearest contour), dist_coast_km."""
    lat, lng = zip(*[h3.cell_to_latlng(c) for c in cells])
    pts = gpd.GeoDataFrame({"cell": cells},
                           geometry=gpd.points_from_xy(lng, lat), crs=4326).to_crs(gp.METRIC_CRS)
    mmi = np.full(len(pts), np.nan)
    for ev, sub in contours.groupby("event"):
        j = gpd.sjoin_nearest(pts[["geometry"]], sub[["value", "geometry"]], how="left")
        j = j[~j.index.duplicated()]  # ties -> first
        mmi = np.fmax(mmi, j["value"].to_numpy())
    pts["mmi"] = mmi
    pts["dist_coast_km"] = pts.geometry.distance(coast) / 1000.0
    return pts.set_index("cell")


# --- Moran's I (hand-rolled: h3 k=1 adjacency, row-standardised, permutation p) ---
def morans_i(cells, values, n_perm=N_PERM):
    idx = {c: i for i, c in enumerate(cells)}
    nbr = [[idx[n] for n in h3.grid_disk(c, 1) if n != c and n in idx] for c in cells]
    keep = np.array([len(n) > 0 for n in nbr])
    z = values - values.mean()
    n = int(keep.sum())
    if n < 30:
        return np.nan, np.nan, n

    def lag(v):  # row-standardised spatial lag
        return np.array([v[nb].mean() if nb else 0.0 for nb in nbr])

    def stat(v):
        zz = v - v.mean()
        return (zz[keep] * lag(zz)[keep]).sum() / (zz[keep] ** 2).sum()

    obs = stat(values)
    perms = np.empty(n_perm)
    v = values.copy()
    for k in range(n_perm):
        RNG.shuffle(v)
        perms[k] = stat(v)
    p = (np.sum(np.abs(perms) >= abs(obs)) + 1) / (n_perm + 1)  # two-sided
    return obs, p, n


def h3_count(gdf_metric, region, res, name):
    sub = gdf_metric[gdf_metric.geometry.representative_point().within(region)]
    if len(sub) == 0:
        return pd.Series(dtype=int, name=name)
    ll = sub.to_crs(4326).geometry.representative_point()
    return pd.Series([h3.latlng_to_cell(p.y, p.x, res) for p in ll]).value_counts().rename(name)


def main():
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    ext = gp.cems_extent()
    ext_latest = gp.to_metric(ext[ext.is_latest == True]).geometry.make_valid().union_all()  # noqa: E712
    base = base_buildings()
    contours = mmi_contours()
    coast = coast_boundary()
    prods = {
        "Microsoft": (gp.to_metric(gp.microsoft()), gp.dissolve_union(gp.microsoft_aoi())),
        "IMPACT v2": (gp.to_metric(gp.impact_v2()), gp.dissolve_union(gp.impact_v2_aoi())),
        "OSU": (gp.to_metric(gp.osu()), gp.dissolve_union(gp.osu_aoi())),
    }

    rows, resid_maps = [], {}
    for res in (8, 7):
        for name, (foot, aoi) in prods.items():
            region = ext_latest.intersection(aoi)
            nb = h3_count(base, region, res, "base")
            df = pd.concat([nb,
                            h3_count(cems, region, res, "cems"),
                            h3_count(foot, region, res, "pdmg")], axis=1).fillna(0)
            df = df[df.base >= 1]  # universe: cells with base buildings (zero-damage kept)
            cov = cell_covariates(df.index.tolist(), res, contours, coast)
            df = df.join(cov[["mmi", "dist_coast_km"]])

            # 1-2. Poisson GLM product ~ log1p(cems); Pearson residuals + dispersion.
            # Two specs: "raw" (NOTES spec) and "exposure" (offset log(base)) — a cell with
            # more buildings hosts more flags at a constant per-building FP rate, so density
            # dependence in the raw spec is partly mechanical; the offset spec isolates the
            # per-building over-detection RATE, the real bias quantity.
            X = sm.add_constant(np.log1p(df.cems.to_numpy()))
            fits = {
                "raw": sm.GLM(df.pdmg.to_numpy(), X, family=sm.families.Poisson()).fit(),
                "exposure": sm.GLM(df.pdmg.to_numpy(), X, family=sm.families.Poisson(),
                                   offset=np.log(df.base.to_numpy())).fit(),
            }

            for spec, fit in fits.items():
                resid = np.asarray(fit.resid_pearson)
                disp = float((resid ** 2).sum() / max(fit.df_resid, 1))

                # 3a. Moran's I on residuals
                mi, mi_p, n_mi = morans_i(df.index.tolist(), resid.copy())

                # 3b. residuals ~ z-scored covariates (OLS, HC1)
                C = pd.DataFrame({
                    "log_bldg": np.log1p(df.base.to_numpy()),
                    "dist_coast": df.dist_coast_km.to_numpy(),
                    "mmi": df.mmi.to_numpy(),
                })
                # drop degenerate covariates (one MMI contour spans a small AOI -> zero variance)
                keep_cov = [k for k in C if C[k].std(ddof=0) > 0 and C[k].notna().all()]
                Cz = (C[keep_cov] - C[keep_cov].mean()) / C[keep_cov].std(ddof=0)
                ols = sm.OLS(resid, sm.add_constant(Cz)).fit(cov_type="HC1")
                uni = {k: spearmanr(C[k], resid)[0] if k in keep_cov else np.nan for k in C}
                coef = lambda k: ols.params.get(k, np.nan)  # noqa: E731
                pval = lambda k: ols.pvalues.get(k, np.nan)  # noqa: E731

                rows.append(dict(
                    res=res, product=name, spec=spec, cells=len(df),
                    dispersion=round(disp, 1),
                    moran_I=round(mi, 3), moran_p=round(mi_p, 4),
                    b_logbldg=round(coef("log_bldg"), 3), p_logbldg=round(pval("log_bldg"), 4),
                    b_coast=round(coef("dist_coast"), 3), p_coast=round(pval("dist_coast"), 4),
                    b_mmi=round(coef("mmi"), 3), p_mmi=round(pval("mmi"), 4),
                    r2=round(ols.rsquared, 3),
                    sp_logbldg=round(uni["log_bldg"], 2), sp_coast=round(uni["dist_coast"], 2),
                    sp_mmi=round(uni["mmi"], 2),
                ))
                print(f"res{res} {name:10s} [{spec:8s}] n={len(df):5d} disp={disp:6.1f} "
                      f"I={mi:.3f} (p={mi_p:.4f})  "
                      f"b: bldg={coef('log_bldg'):+.3f} coast={coef('dist_coast'):+.3f} "
                      f"mmi={coef('mmi'):+.3f}  R2={ols.rsquared:.3f}")
                if res == 8 and spec == "exposure":
                    ll = np.array([h3.cell_to_latlng(c) for c in df.index])
                    resid_maps[name] = (ll[:, 1], ll[:, 0], resid)

    out = pd.DataFrame(rows)
    csv = os.path.join(os.path.dirname(__file__), "..", "rq3_error_structure_summary.csv")
    out.to_csv(csv, index=False)
    for spec in ("raw", "exposure"):
        print(f"\n== res 8 [{spec}] ==\n",
              out[(out.res == 8) & (out.spec == spec)].to_string(index=False))
    print("wrote", csv)

    # stacked vertically so each panel autoscales to full width (side-by-side squeezed the
    # wide SAR swaths into illegible ribbons); CODAB coastline for geographic reference
    from matplotlib.patches import Polygon as MplPolygon
    land = gp.codab(0).geometry.make_valid().union_all()
    fig, ax = plt.subplots(3, 1, figsize=(11, 13))
    for i, (name, (x, y, r)) in enumerate(resid_maps.items()):
        pad_x = (x.max() - x.min()) * 0.03
        pad_y = (y.max() - y.min()) * 0.08
        ax[i].set_facecolor("#e7f0f6")
        for g in getattr(land, "geoms", [land]):
            ax[i].add_patch(MplPolygon(np.asarray(g.exterior.coords), closed=True,
                                       facecolor="#f1f0ea", edgecolor="#b9b7ae",
                                       lw=1.0, zorder=0))
        lim = np.percentile(np.abs(r), 98) or 1
        sc = ax[i].scatter(x, y, c=r, s=22, cmap="RdBu_r", vmin=-lim, vmax=lim, zorder=3)
        ax[i].set_title(name, fontsize=12)
        ax[i].set_aspect("equal")
        ax[i].set_xlim(x.min() - pad_x, x.max() + pad_x)
        ax[i].set_ylim(y.min() - pad_y, y.max() + pad_y)
        plt.colorbar(sc, ax=ax[i], shrink=0.85, pad=0.01, label="Pearson residual")
    fig.suptitle("RQ3b error structure — exposure-adjusted GLM residuals per H3 res-8 cell\n"
                 "(red = per-building over-detection beyond CEMS-explained; clumps = spatial bias)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq3_residual_maps_res8.png"), dpi=150)
    print("wrote figs/rq3_residual_maps_res8.png")


if __name__ == "__main__":
    main()
