"""RQ8d — is the null's coast-distance covariate fair? Feature ablation (external review).

Objection (2026-09-02): distance to coast looks event-specific, "chosen because it works
here". This ablates the null's feature set on the frozen core buildings, with the exact
rq3f null pipeline (logistic, class_weight=balanced, GroupKFold(5) on res-7 cells,
per-fold standardization). Building-level AP / best-F1 and core ranking rho (res 8/9).

Arms:
    dens                          density alone — nothing event-specific at all
    dens+mmi                      + ShakeMap MMI (integer contour bands)
    dens+coast+mmi                the paper's null    <- ANCHOR: rq3f core rho .648/.478
    dens+rupt+mmi                 coast swapped for distance to the M7.5 finite-fault
                                  SURFACE PROJECTION — documented DEAD END: the core sits
                                  ON the rupture polygon (median distance 0, max 1.6 km),
                                  so the feature degenerates into "metres north of the
                                  polygon edge", an accidental beachfront detector with a
                                  physically backwards sign. Kept as a cautionary row.
    dens+slope+mmi                Copernicus GLO-30 slope (the Wald-Allen Vs30 proxy)
    dens+elev+mmi                 GLO-30 elevation — in this geography the low surfaces
                                  ARE the 1999-mapped debris-flow fans (Wieczorek et al.
                                  OFR 01-0144; I-2772), i.e. a substrate covariate
    dens+slope+elev+mmi           the fully generalizable DEM null
    dens+slope+elev+coast+mmi     does coast add anything beyond the DEM?
    dens+sand+clay+mmi            (--with-soil) SoilGrids 0-5 cm texture. SoilGrids masks
                                  built-up land: 86% of core buildings sample NoData and
                                  are nearest-filled (median 310 m) — the arm shows global
                                  soil products cannot see inside a city at this scale.

Headline (2026-09-02 run): MMI contributes nothing (one band covers the core); soil
contributes nothing; elevation alone BEATS the paper's coast null (F1 .143 vs .127,
rho8 .706 vs .648) and once slope+elevation are in, coast adds ~nothing. Even the
density-only null stays inside the product band (F1 .086 vs products .085-.148). The
paper's conclusions do not hinge on the coast covariate; a purely generalizable DEM
null is slightly stronger.

DEM: Copernicus GLO-30 tile N10/W067, auto-downloaded from the AWS open-data bucket to
_cache/ (untracked) on first run.

Run: uv run --group etl --with scikit-learn --with scipy --with rasterio python \
       exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8d_null_ablation.py [--with-soil]
"""
from __future__ import annotations
import json, os, sys, urllib.request

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import rasterio
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.model_selection import GroupKFold

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402
import ocha_stratus as stratus  # noqa: E402

HERE = os.path.dirname(__file__)
CACHE = os.path.join(HERE, "..", "_cache")
os.makedirs(CACHE, exist_ok=True)
WITH_SOIL = "--with-soil" in sys.argv[1:]
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_N10_00_W067_00_DEM/"
           "Copernicus_DSM_COG_10_N10_00_W067_00_DEM.tif")


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
    d = pd.read_parquet(os.path.join(HERE, "..", "rq8_oof_scores_r10.parquet"))
    bld = gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d.lon, d.lat), crs=4326
                           ).to_crs(gp.METRIC_CRS)
    y = d.y.to_numpy()
    ll = bld.to_crs(4326)
    cell7 = np.array([h3.latlng_to_cell(p.y, p.x, 7) for p in ll.geometry])
    cell8 = np.array([h3.latlng_to_cell(p.y, p.x, 8) for p in ll.geometry])
    cell9 = np.array([h3.latlng_to_cell(p.y, p.x, 9) for p in ll.geometry])
    dens = pd.Series(cell9).map(pd.Series(cell9).value_counts()).to_numpy()
    coast = gp.to_metric(gp.codab(0)).geometry.make_valid().union_all().boundary
    dist_coast = bld.geometry.distance(coast).to_numpy() / 1000.0

    # MMI, rq3f construction (max of both events' contour bands)
    frames = []
    for ev in ("us6000t7zp", "us6000t7zc"):
        raw = json.loads(stratus.load_blob_data(
            gp.S.blob_path("bronze", "source=usgs", "adm0=VE", f"event={ev}",
                           "cont_mi.json", event=None),
            stage="dev", container_name=gp.S.container))
        g = gpd.GeoDataFrame.from_features(raw["features"], crs=4326).to_crs(gp.METRIC_CRS)
        frames.append(g[["value", "geometry"]])
    mmi = np.full(len(d), np.nan)
    for g in frames:
        j = gpd.sjoin_nearest(bld[["geometry"]], g, how="left")
        j = j[~j.index.duplicated()]
        mmi = np.fmax(mmi, j["value"].to_numpy())
    mmi = np.nan_to_num(mmi, nan=np.nanmedian(mmi))

    # rupture surface-projection distance (the documented dead end)
    raw = json.loads(stratus.load_blob_data(
        gp.S.blob_path("bronze", "source=usgs", "adm0=VE", "event=us6000t7zp",
                       "rupture.json", event=None),
        stage="dev", container_name=gp.S.container))
    rg = gpd.GeoDataFrame.from_features(raw["features"], crs=4326).to_crs(gp.METRIC_CRS)
    dist_rupt = bld.geometry.distance(rg.geometry.make_valid().union_all()).to_numpy() / 1000.0

    # DEM elevation + slope (auto-fetch tile)
    dem_path = os.path.join(CACHE, "GLO30_N10_W067.tif")
    if not os.path.exists(dem_path):
        print("downloading Copernicus GLO-30 N10/W067 ...")
        urllib.request.urlretrieve(DEM_URL, dem_path)
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype("float64")
        tr = src.transform
        dy = abs(tr.e) * 110_540
        dx = abs(tr.a) * 111_320 * np.cos(np.deg2rad(10.6))
        gy, gx = np.gradient(dem, dy, dx)
        slope_g = np.degrees(np.arctan(np.hypot(gx, gy)))
        rows, cols = rasterio.transform.rowcol(tr, d.lon.values, d.lat.values)
        rows = np.clip(rows, 0, dem.shape[0] - 1)
        cols = np.clip(cols, 0, dem.shape[1] - 1)
        elev = dem[rows, cols]
        slope = slope_g[rows, cols]

    FEATS = {"dens": [dens],
             "dens+mmi": [dens, mmi],
             "dens+coast+mmi (paper)": [dens, dist_coast, mmi],
             "dens+rupt+mmi (dead end)": [dens, dist_rupt, mmi],
             "dens+slope+mmi": [dens, slope, mmi],
             "dens+elev+mmi": [dens, elev, mmi],
             "dens+slope+elev+mmi": [dens, slope, elev, mmi],
             "dens+slope+elev+coast+mmi": [dens, slope, elev, dist_coast, mmi]}

    if WITH_SOIL:
        from rasterio.vrt import WarpedVRT
        from rasterio.windows import from_bounds
        soil = {}
        bbox = (d.lon.min() - 0.02, d.lat.min() - 0.02, d.lon.max() + 0.02, d.lat.max() + 0.02)
        for prop in ("sand", "clay"):
            url = (f"/vsicurl/https://files.isric.org/soilgrids/latest/data/{prop}/"
                   f"{prop}_0-5cm_mean.vrt")
            with rasterio.open(url) as src, WarpedVRT(src, crs="EPSG:4326") as vrt:
                win = from_bounds(*bbox, vrt.transform)
                arr = vrt.read(1, window=win)
                wt = vrt.window_transform(win)
                rr, cc = rasterio.transform.rowcol(wt, d.lon.values, d.lat.values)
                rr = np.clip(rr, 0, arr.shape[0] - 1)
                cc = np.clip(cc, 0, arr.shape[1] - 1)
                v = arr[rr, cc].astype("float64")
                v[v < 0] = np.nan
                ok = ~np.isnan(v)
                print(f"soil {prop}: {ok.mean():.0%} of buildings have data "
                      "(SoilGrids masks built-up land); nearest-filling the rest")
                xy = np.c_[bld.geometry.x, bld.geometry.y]
                t = cKDTree(xy[ok])
                _, idx = t.query(xy[~ok], k=1)
                v[~ok] = v[ok][idx]
                soil[prop] = v
        FEATS["dens+sand+clay+mmi (soil)"] = [dens, soil["sand"], soil["clay"], mmi]

    # CEMS counts per core cell (rq3f core construction)
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin((2, 3))]
    region = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    for a in (gp.dissolve_union(gp.microsoft_aoi()), gp.dissolve_union(gp.impact_v2_aoi()),
              gp.dissolve_union(gp.osu_aoi()), uh_aoi(),
              gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                            "analysed_extent.parquet"))):
        region = region.intersection(a)
    cll = (cems[cems.geometry.representative_point().within(region)]
           .to_crs(4326).geometry.representative_point())

    rows_out = []
    for nm, cols_ in FEATS.items():
        X = np.c_[tuple(cols_)]
        oof = np.zeros(len(d))
        for tr_, te in GroupKFold(n_splits=5).split(X, y, cell7):
            mu, sd = X[tr_].mean(0), X[tr_].std(0) + 1e-9
            m = LogisticRegression(max_iter=2000, class_weight="balanced")
            m.fit((X[tr_] - mu) / sd, y[tr_])
            oof[te] = m.predict_proba((X[te] - mu) / sd)[:, 1]
        ap = average_precision_score(y, oof)
        p, r, _ = precision_recall_curve(y, oof)
        f1 = np.divide(2 * p * r, p + r, out=np.zeros_like(p), where=(p + r) > 0)
        i = int(np.argmax(f1))
        row = dict(features=nm, AP=round(float(ap), 3), best_F1=round(float(f1[i]), 3),
                   P=round(float(p[i]), 3), R=round(float(r[i]), 3))
        for res, arr in ((8, cell8), (9, cell9)):
            cnt = pd.Series([h3.latlng_to_cell(pp.y, pp.x, res) for pp in cll]).value_counts()
            base = pd.Series(arr).value_counts()
            t = pd.concat([cnt.rename("cems"), base.rename("n")], axis=1).fillna(0)
            t = t[t.n > 0]
            s = pd.Series(oof, index=arr).groupby(level=0).sum().reindex(t.index).fillna(0)
            row[f"rho_res{res}"] = round(float(spearmanr(t.cems, s)[0]), 3)
        rows_out.append(row)
        print(row)

    out = pd.DataFrame(rows_out)
    paper = out[out.features == "dens+coast+mmi (paper)"].iloc[0]
    if not (paper.rho_res8 == 0.648 and paper.rho_res9 == 0.478):
        raise SystemExit(f"ANCHOR FAILED vs rq3f core null: got "
                         f"{paper.rho_res8}/{paper.rho_res9}, frozen 0.648/0.478")
    print("anchor OK: the paper arm reproduces the rq3f core null exactly")
    out.to_csv(os.path.join(HERE, "..", "rq8d_null_ablation.csv"), index=False)
    print("wrote rq8d_null_ablation.csv")


if __name__ == "__main__":
    main()
