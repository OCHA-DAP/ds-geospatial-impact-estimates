"""0005 step 11a — scale the facet watch to the central Himalaya arc.

Domain: 82-89E x 26.8-30.2N (~25x the Langtang pilot area). Two-tier design —
the full per-acquisition series behind the validated worst-3-run statistic
cannot be pulled for every facet at this scale through the interactive API, so:

  tier 1 (this script, all facets): per facet x year, the SEASON-MEAN of
    morning-pass (descending) VV over Jun 1 - Aug 25, computed entirely
    server-side — one composite reduction per year per facet block, one number
    per facet-year over the wire. A screening statistic: cheaper and blunter
    than the validated detector (it mixes orbits and ignores run structure),
    used only to rank.
  tier 2 (himalaya_tier2.py): the full validated statistic on tier 1's worst
    facets only.

Steps here: (1) enumerate facets for the whole domain (same recipe as
facets_prototype.py, tiled into blocks to stay under GEE's vectorization caps),
(2) tier-1 season means 2020-2026, (3) a domain hillshade for the dashboard.

Run: uv run --group etl --with earthengine-api,geopandas python \
       exploratory/0005-nepal-glof-sar-precursor/himalaya_extract.py
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
import urllib.request

import ee

from extract import init_ee, s1

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# Nepal core first (Annapurna..Everest..Kanchenjunga edge): the full 82-89E arc
# enumerated at 30 m through the interactive API measured ~45 min per block —
# 10+ hours total. This domain at 60 m is the tractable first increment; the
# full arc goes via GEE batch exports when it goes at all.
DOMAIN = [84.0, 27.3, 87.0, 29.3]
BLOCKS_X, BLOCKS_Y = 3, 2
VEC_SCALE = 60  # vectorization scale, m (0.25 km2 ~ 69 px at 60 m)
SLOPE_MIN, ELEV_MIN = 25, 4500
MIN_KM2, MAX_KM2 = 0.5, 4.0
SEASON = ("-06-01", "-08-26")
YEARS = range(2020, 2027)
STAT_BATCH = 400  # facets per reduceRegions call (one row each -> far under caps)


def enumerate_block(region: list[float]) -> list[dict]:
    rect = ee.Geometry.Rectangle(region)
    g = (
        ee.FeatureCollection("GLIMS/20230607")
        .filterBounds(rect)
        .filter(ee.Filter.eq("line_type", "glac_bound"))
    )
    latest = g.reduceColumns(
        ee.Reducer.max().group(groupField=1, groupName="glac_id"), ["anlys_id", "glac_id"]
    ).get("groups")
    ids = ee.List(latest).map(lambda d: ee.Dictionary(d).get("max"))
    g = g.filter(ee.Filter.inList("anlys_id", ids))
    coll = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM")
    dem = coll.mosaic().setDefaultProjection(coll.first().projection())
    slope = ee.Terrain.slope(dem)
    aspect = ee.Terrain.aspect(dem)
    ice = ee.Image(0).byte().paint(g, 1).focalMax(radius=200, units="meters")
    rad = aspect.multiply(math.pi / 180)
    sy = rad.sin().focalMean(300, "circle", "meters")
    cx = rad.cos().focalMean(300, "circle", "meters")
    smooth_deg = sy.atan2(cx).multiply(180 / math.pi).add(360).mod(360)
    octant = smooth_deg.add(22.5).divide(45).floor().mod(8).add(1).byte()
    mask = ice.eq(1).And(slope.gte(SLOPE_MIN)).And(dem.gte(ELEV_MIN))
    labeled = octant.updateMask(mask).rename("aspect8")
    min_px = int(0.25e6 / VEC_SCALE**2)
    labeled = labeled.updateMask(
        labeled.connectedPixelCount(min_px + 30, True).gte(min_px))
    feats = []
    for o in range(1, 9):
        fc = labeled.updateMask(labeled.eq(o)).reduceToVectors(
            geometry=rect, scale=VEC_SCALE, geometryType="polygon", eightConnected=True,
            labelProperty="aspect8", maxPixels=1e10,
        )
        for attempt in range(4):
            try:
                feats.extend(fc.getInfo()["features"])
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    raise RuntimeError(f"block {region} octant {o}: {e}") from e
                time.sleep(20 * (attempt + 1))
    return feats


def enumerate_domain() -> str:
    dst = os.path.join(DATA, "facets_himalaya.geojson")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        print("domain facets exist, skipped")
        return dst
    W, S, E, N = DOMAIN
    dx, dy = (E - W) / BLOCKS_X, (N - S) / BLOCKS_Y
    feats = []
    for i in range(BLOCKS_X):
        for j in range(BLOCKS_Y):
            block = [W + i * dx, S + j * dy, W + (i + 1) * dx, S + (j + 1) * dy]
            got = enumerate_block(block)
            feats.extend(got)
            print(f"block {i},{j}: +{len(got)} components (total {len(feats)})", flush=True)
    with open(dst, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    return dst


def shape(path: str):
    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import box as sbox

    gdf = gpd.read_file(path).set_crs(4326)
    utm = gdf.to_crs(32645)
    utm["km2"] = utm.geometry.area / 1e6
    utm = utm[utm.km2 >= MIN_KM2].copy()
    out = []
    for _, r in utm.iterrows():
        if r.km2 <= MAX_KM2:
            out.append((r.geometry, int(r.aspect8)))
            continue
        minx, miny, maxx, maxy = r.geometry.bounds
        x = minx
        while x < maxx:
            y = miny
            while y < maxy:
                t = r.geometry.intersection(sbox(x, y, x + 2000, y + 2000))
                if not t.is_empty and t.area / 1e6 >= MIN_KM2 / 2:
                    out.append((t, int(r.aspect8)))
                y += 2000
            x += 2000
    facets = gpd.GeoDataFrame(
        pd.DataFrame({"aspect8": [a for _, a in out]}),
        geometry=[g for g, _ in out], crs=32645).to_crs(4326)
    facets["facet_id"] = [f"H{i:05d}" for i in range(len(facets))]
    facets["km2"] = facets.to_crs(32645).geometry.area / 1e6
    aspects = "N NE E SE S SW W NW".split()
    facets["aspect"] = facets.aspect8.map(lambda a: aspects[a - 1])
    dst = os.path.join(DATA, "facets_himalaya_final.geojson")
    facets.to_file(dst, driver="GeoJSON")
    print(f"domain facets: {len(facets)} (median {facets.km2.median():.2f} km2, "
          f"total {facets.km2.sum():.0f} km2)")
    return facets


def tier1_stats(facets) -> None:
    dst = os.path.join(DATA, "himalaya_tier1.csv")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        print("tier-1 stats exist, skipped")
        return
    batches = []
    for b0 in range(0, len(facets), STAT_BATCH):
        sub = facets.iloc[b0:b0 + STAT_BATCH]
        batches.append(ee.FeatureCollection([
            ee.Feature(ee.Geometry(g.__geo_interface__), {"facet_id": fid})
            for g, fid in zip(sub.geometry, sub.facet_id)
        ]))
    with open(dst, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["facet_id", "year", "vv_db", "n_img"])
        for year in YEARS:
            col = (s1().filterDate(f"{year}{SEASON[0]}", f"{year}{SEASON[1]}")
                   .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
                   .select("VV"))
            n_img = col.filterBounds(ee.Geometry.Rectangle(DOMAIN)).size().getInfo()
            comp = col.mean()
            for bi, fc in enumerate(batches):
                rr = comp.reduceRegions(fc, ee.Reducer.mean(), 30)
                for attempt in range(5):
                    try:
                        got = rr.getInfo()["features"]
                        break
                    except Exception as e:  # noqa: BLE001
                        if attempt == 4:
                            raise RuntimeError(f"tier1 {year} b{bi}: {e}") from e
                        time.sleep(20 * (attempt + 1))
                for r in got:
                    p = r["properties"]
                    if p.get("mean") is not None:
                        w.writerow([p["facet_id"], year, round(p["mean"], 3), n_img])
                print(f"tier1 {year} b{bi}: {len(got)}", flush=True)
    print(f"-> {dst}")


def hillshade() -> None:
    dst = os.path.join(DATA, "himalaya_hillshade.tif")
    if os.path.exists(dst):
        return
    coll = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM")
    dem = coll.mosaic().setDefaultProjection(coll.first().projection())
    img = ee.Terrain.hillshade(dem, 315, 40).toFloat()
    url = img.getDownloadURL({"scale": 300, "region": ee.Geometry.Rectangle(DOMAIN),
                              "format": "GEO_TIFF", "crs": "EPSG:4326"})
    urllib.request.urlretrieve(url, dst)
    print(f"hillshade -> {dst} ({os.path.getsize(dst) / 1e6:.1f} MB)")


if __name__ == "__main__":
    init_ee()
    facets = shape(enumerate_domain())
    hillshade()
    tier1_stats(facets)
