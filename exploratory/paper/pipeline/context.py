"""Context (geography) features for the geography null and the weighted fusion — ONE definition.

The null is "the fusion with the product inputs removed" (ADR-0025), so both must draw the same
context variables from one place. Until 2026-09-17 four scripts each carried their own copy
(ranking.py, rq8_learned_fusion.py, rq8b_asdelivered_baseline.py, rq8d_null_ablation.py) and the
feature set was density + coast distance + ShakeMap MMI. The rq8d ablation (findings register,
2026-09-02) showed coast distance was never load-bearing and that a null on globally available
terrain is stronger; ADR-0033 moves the brief's null to:

    NULL_FEATURES = density9, slope, elev, mmi

  density9   buildings per H3 res-9 cell (built-up density)
  slope      Copernicus GLO-30 slope, degrees (the Wald-Allen Vs30 proxy)
  elev       Copernicus GLO-30 elevation, metres (in La Guaira the low surfaces ARE the 1999-mapped
             debris-flow fans: a substrate covariate)
  mmi        USGS ShakeMap intensity, max over the two events, nearest contour (the hazard term;
             flat across the core, a quarter to a third of the weight across delivered footprints)

`dist_coast` is still computed on request (include_coast=True) for the archived ablation and for
oracle comparisons; it is NOT in NULL_FEATURES.

DEM tiles are fetched from the Copernicus open-data bucket into artefacts/_cache/ (untracked) on
first use, one 1°x1° tile per cell the points touch, and sampled from a mosaic. Every point must
land inside the mosaic and sample a finite, non-nodata value; otherwise this raises — a silently
clipped or filled elevation would put a wrong number into every downstream model.

This module is a Snakemake input ONLY to the rules that fit a null (ranking, rq8, rq8b), never to
scorecards/facts, so a change here cannot trigger the precision or pair numbers.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request

import geopandas as gpd
import h3
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import gie_paper as gp  # noqa: E402

NULL_FEATURES = ["density9", "slope", "elev", "mmi"]
USGS_EVENTS = ("us6000t7zp", "us6000t7zc")
CACHE = os.path.join(HERE, "..", "artefacts", "_cache")
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM/Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM.tif")
NODATA_FLOOR = -1000.0   # GLO-30 nodata is -32767; no building in this study area sits below sea level


def _tile_name(lat: float, lon: float) -> tuple[str, str]:
    la, lo = int(np.floor(lat)), int(np.floor(lon))
    return (f"{'N' if la >= 0 else 'S'}{abs(la):02d}", f"{'E' if lo >= 0 else 'W'}{abs(lo):03d}")


def dem_tiles(lons: np.ndarray, lats: np.ndarray) -> list[str]:
    """Local paths of every GLO-30 tile the points touch, downloading missing ones."""
    os.makedirs(CACHE, exist_ok=True)
    paths = []
    for la, lo in sorted({_tile_name(a, o) for a, o in zip(lats, lons)}):
        p = os.path.join(CACHE, f"GLO30_{la}_{lo}.tif")
        if not os.path.exists(p):
            print(f"context: downloading Copernicus GLO-30 {la}/{lo} ...", flush=True)
            url = DEM_URL.format(lat=la, lon=lo)
            try:
                urllib.request.urlretrieve(url, p + ".part")
            except urllib.error.HTTPError as e:
                n = int(sum(_tile_name(a, o) == (la, lo) for a, o in zip(lats, lons)))
                raise RuntimeError(f"context: no GLO-30 tile {la}/{lo} in the Copernicus bucket (HTTP {e.code}); "
                                   f"{n} points fall in it. Open-ocean cells have no tile — are these points on land? {url}") from e
            os.replace(p + ".part", p)   # a partial download must never be mistaken for a tile
        paths.append(p)
    return paths


def terrain(lons: np.ndarray, lats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(elev_m, slope_deg) sampled at lon/lat from the GLO-30 tiles. Fails loudly on any gap."""
    import rasterio
    from rasterio.merge import merge
    srcs = [rasterio.open(p) for p in dem_tiles(lons, lats)]
    try:
        dem, tr = merge(srcs)
    finally:
        for s in srcs:
            s.close()
    dem = dem[0].astype("float64")
    # pixel size in metres, per row (latitude), so slope is a true angle everywhere in the mosaic
    row_lat = tr.f + tr.e * (np.arange(dem.shape[0]) + 0.5)
    dy = abs(tr.e) * 110_540.0
    dx = (abs(tr.a) * 111_320.0 * np.cos(np.deg2rad(row_lat)))[:, None]
    gy = np.gradient(dem, dy, axis=0)
    gx = np.gradient(dem, axis=1) / dx
    slope_g = np.degrees(np.arctan(np.hypot(gx, gy)))
    rows, cols = rasterio.transform.rowcol(tr, lons, lats)
    rows, cols = np.asarray(rows), np.asarray(cols)
    inside = (rows >= 0) & (rows < dem.shape[0]) & (cols >= 0) & (cols < dem.shape[1])
    if not inside.all():
        raise RuntimeError(f"context: {(~inside).sum()} points fall outside the DEM mosaic")
    elev, slope = dem[rows, cols], slope_g[rows, cols]
    bad = ~np.isfinite(elev) | (elev < NODATA_FLOOR) | ~np.isfinite(slope)
    if bad.any():
        raise RuntimeError(f"context: {bad.sum()} points sample DEM nodata")
    return elev, slope


def shakemap_mmi(d: gpd.GeoDataFrame) -> np.ndarray:
    """Nearest ShakeMap contour value, max over events; NaN (outside all contours) -> median."""
    import ocha_stratus as stratus
    mmi = np.full(len(d), np.nan)
    for ev in USGS_EVENTS:
        raw = json.loads(stratus.load_blob_data(
            gp.S.blob_path("bronze", "source=usgs", "adm0=VE", f"event={ev}", "cont_mi.json", event=None),
            stage="dev", container_name=gp.S.container))
        g = gpd.GeoDataFrame.from_features(raw["features"], crs=4326).to_crs(gp.METRIC_CRS)[["value", "geometry"]]
        j = gpd.sjoin_nearest(d[["geometry"]], g, how="left")
        j = j[~j.index.duplicated()]
        mmi = np.fmax(mmi, j["value"].to_numpy())
    return np.nan_to_num(mmi, nan=np.nanmedian(mmi))


def context_features(d: gpd.GeoDataFrame, include_coast: bool = False) -> gpd.GeoDataFrame:
    """Add NULL_FEATURES (and dist_coast if asked) to a buildings frame in the metric CRS.

    Location is the representative point of the frame geometry (ADR-0030 convention)."""
    d = d.copy()
    rp = d.geometry.representative_point()
    ll = gpd.GeoSeries(rp, crs=gp.METRIC_CRS).to_crs(4326)
    lons, lats = ll.x.to_numpy(), ll.y.to_numpy()
    cell9 = pd.Series([h3.latlng_to_cell(la, lo, 9) for la, lo in zip(lats, lons)])
    d["density9"] = cell9.map(cell9.value_counts()).to_numpy()
    d["elev"], d["slope"] = terrain(lons, lats)
    d["mmi"] = shakemap_mmi(d)
    if include_coast:
        coast = gp.to_metric(gp.codab(0)).geometry.make_valid().union_all().boundary
        d["dist_coast"] = d.geometry.distance(coast) / 1000.0
    return d
