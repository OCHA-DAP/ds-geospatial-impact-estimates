"""0005 step 13 — batch-export pipeline for the full-arc facet watch.

The interactive API measured ~45 min per pilot-sized block just to ENUMERATE
facets (10+ h for the 82-89E arc). This pipeline moves all heavy compute into
GEE batch Export tasks, which run server-side: submit, turn the laptop off,
come back later. Progress is visible at code.earthengine.google.com/tasks.

Resumable state machine — run the same command repeatedly; each run advances
whatever is ready:

  phase A  submit facet-enumeration exports (one task per block) -> EE assets
  phase B  when all A-assets exist: submit tier-1 exports (one task per year:
           season-mean descending VV reduced over every facet) -> EE assets
  phase C  when all B-assets exist: download stats + simplified geometries
           (small, chunked reads of precomputed tables), write
           data/facets_himalaya_final.geojson + data/himalaya_tier1.csv —
           then himalaya_tier2.py / hazard_chain.py / himalaya_build.py run
           as before (minutes).

Server-side facet recipe (all-final, no client shaping): GLIMS ice + 200 m
buffer, slope >= 25, elev >= 4500, aspect smoothed 300 m and octanted, the
octant label composited with a 0.02-degree grid key so no facet exceeds
~2.2 km — connected components >= 0.25 km2 vectorized at 30 m.

Run: uv run --group etl --with earthengine-api,geopandas python \
       exploratory/0005-nepal-glof-sar-precursor/himalaya_batch.py
"""
from __future__ import annotations

import csv
import json
import math
import os
import time

import ee

from extract import init_ee, s1

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

DOMAIN = [82.0, 26.8, 89.0, 30.2]
BLOCKS_X, BLOCKS_Y = 5, 3
SLOPE_MIN, ELEV_MIN = 25, 4500
GRID_DEG = 0.02  # server-side split cell (~2.2 km)
MIN_PX = 278     # 0.25 km2 at 30 m
SEASON = ("-06-01", "-08-26")
YEARS = range(2020, 2027)
FOLDER = "projects/ee-zackarno/assets/gie0005"


def ensure_folder() -> None:
    try:
        ee.data.getAsset(FOLDER)
    except Exception:  # noqa: BLE001 — asset probe; create on miss
        ee.data.createAsset({"type": "Folder"}, FOLDER)
        print(f"created asset folder {FOLDER}")


def asset_exists(path: str) -> bool:
    try:
        ee.data.getAsset(path)
        return True
    except Exception:  # noqa: BLE001
        return False


def running_tasks() -> dict[str, str]:
    out = {}
    for t in ee.data.getTaskList():
        if t["state"] in ("READY", "RUNNING"):
            out[t.get("description", "")] = t["state"]
    return out


def empty_blocks() -> set[str]:
    """Blocks whose export FAILED with 'Table is empty' — a correct result (no
    glacierized faces there, e.g. the Terai row), not an error. Absence of
    facets is a real state of the world; treat it as done, never resubmit."""
    out = set()
    for t in ee.data.getTaskList():
        if (t["state"] == "FAILED"
                and "Table is empty" in t.get("error_message", "")):
            out.add(t.get("description", ""))
    return out


def facet_image(region: ee.Geometry) -> ee.Image:
    g = (
        ee.FeatureCollection("GLIMS/20230607")
        .filterBounds(region)
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
    octant = (sy.atan2(cx).multiply(180 / math.pi).add(360).mod(360)
              .add(22.5).divide(45).floor().mod(8).add(1))
    ll = ee.Image.pixelLonLat()
    cellx = ll.select("longitude").subtract(DOMAIN[0]).divide(GRID_DEG).floor()
    celly = ll.select("latitude").subtract(DOMAIN[1]).divide(GRID_DEG).floor()
    key = cellx.multiply(200).add(celly).multiply(8).add(octant).int()
    mask = ice.eq(1).And(slope.gte(SLOPE_MIN)).And(dem.gte(ELEV_MIN))
    lab = key.updateMask(mask).rename("fkey")
    return lab.updateMask(lab.connectedPixelCount(MIN_PX + 30, True).gte(MIN_PX))


def submit_facets() -> tuple[int, int]:
    W, S, E, N = DOMAIN
    dx, dy = (E - W) / BLOCKS_X, (N - S) / BLOCKS_Y
    tasks = running_tasks()
    empties = empty_blocks()
    submitted = done = 0
    for i in range(BLOCKS_X):
        for j in range(BLOCKS_Y):
            name = f"facets_arc_{i}_{j}"
            asset = f"{FOLDER}/{name}"
            if asset_exists(asset) or name in empties:
                done += 1
                continue
            if name in tasks:
                continue
            rect = ee.Geometry.Rectangle(
                [W + i * dx, S + j * dy, W + (i + 1) * dx, S + (j + 1) * dy])
            fc = facet_image(rect).reduceToVectors(
                geometry=rect, scale=30, geometryType="polygon", eightConnected=True,
                labelProperty="fkey", maxPixels=1e12,
            )
            ee.batch.Export.table.toAsset(fc, description=name, assetId=asset).start()
            submitted += 1
            print(f"submitted {name}")
    return done, BLOCKS_X * BLOCKS_Y


def merged_facets() -> ee.FeatureCollection:
    fcs = [ee.FeatureCollection(f"{FOLDER}/facets_arc_{i}_{j}")
           for i in range(BLOCKS_X) for j in range(BLOCKS_Y)
           if asset_exists(f"{FOLDER}/facets_arc_{i}_{j}")]
    fc = fcs[0]
    for x in fcs[1:]:
        fc = fc.merge(x)
    # stable id from the grid key + a running index within key duplicates is
    # unnecessary: fkey is unique per (cell, octant) and blocks don't overlap
    return fc.map(lambda f: f.set("facet_id",
                                  ee.String("A").cat(ee.Number(f.get("fkey")).format("%d"))))


def submit_tier1() -> tuple[int, int]:
    fc = merged_facets()
    tasks = running_tasks()
    done = submitted = 0
    for year in YEARS:
        name = f"tier1_arc_{year}"
        asset = f"{FOLDER}/{name}"
        if asset_exists(asset):
            done += 1
            continue
        if name in tasks:
            continue
        comp = (s1().filterDate(f"{year}{SEASON[0]}", f"{year}{SEASON[1]}")
                .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
                .select("VV").mean())
        # toAsset refuses null-geometry features — carry a centroid point
        stats = comp.reduceRegions(fc, ee.Reducer.mean(), 30).map(
            lambda f: ee.Feature(f.geometry().centroid(100),
                                 {"facet_id": f.get("facet_id"),
                                  "year": year, "vv_db": f.get("mean")}))
        ee.batch.Export.table.toAsset(stats, description=name, assetId=asset).start()
        submitted += 1
        print(f"submitted {name}")
    return done, len(list(YEARS))


def collect() -> None:
    t1_dst = os.path.join(DATA, "himalaya_tier1.csv")
    if not os.path.exists(t1_dst):
        rows = []
        for year in YEARS:
            fc = ee.FeatureCollection(f"{FOLDER}/tier1_arc_{year}").filter(
                ee.Filter.notNull(["vv_db"]))
            n = fc.size().getInfo()
            lst = fc.toList(n)
            for off in range(0, n, 4000):
                chunk = ee.FeatureCollection(lst.slice(off, off + 4000)).getInfo()["features"]
                rows.extend((r["properties"]["facet_id"], r["properties"]["year"],
                             round(r["properties"]["vv_db"], 3)) for r in chunk)
            print(f"tier1 {year}: {n} rows", flush=True)
        with open(t1_dst, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["facet_id", "year", "vv_db", "n_img"])
            for r in rows:
                w.writerow([r[0], r[1], r[2], ""])
        print(f"-> {t1_dst}")

    geo_dst = os.path.join(DATA, "facets_himalaya_final.geojson")
    if not os.path.exists(geo_dst):
        import geopandas as gpd

        fc = merged_facets().map(
            lambda f: ee.Feature(f.geometry().simplify(60),
                                 {"facet_id": f.get("facet_id"),
                                  "fkey": f.get("fkey")}))
        n = fc.size().getInfo()
        print(f"facets: {n} — downloading simplified geometries", flush=True)
        feats = []
        lst = fc.toList(n)
        for off in range(0, n, 1500):
            feats.extend(ee.FeatureCollection(lst.slice(off, off + 1500))
                         .getInfo()["features"])
            print(f"  {len(feats)}/{n}", flush=True)
        gdf = gpd.GeoDataFrame.from_features(feats, crs=4326)
        gdf["km2"] = gdf.to_crs(32645).geometry.area / 1e6
        aspects = "N NE E SE S SW W NW".split()
        gdf["aspect"] = gdf.fkey.astype(int).mod(8).map(
            lambda a: aspects[a - 1 if a >= 1 else 7])
        gdf.to_file(geo_dst, driver="GeoJSON")
        print(f"-> {geo_dst}")
    print("\ncollected. Next (minutes each):\n"
          "  uv run --group etl --with earthengine-api,geopandas python himalaya_tier2.py\n"
          "  uv run --group etl --with earthengine-api,geopandas python hazard_chain.py "
          "data/facets_himalaya_final.geojson\n"
          "  uv run --group etl --with rasterio,matplotlib,geopandas python himalaya_build.py")


def main() -> None:
    init_ee()
    ensure_folder()
    a_done, a_total = submit_facets()
    print(f"phase A (facet exports): {a_done}/{a_total} assets ready")
    if a_done < a_total:
        print("-> facet exports running in GEE's cloud. You can turn this machine "
              "off; rerun this script later to advance. Task list: "
              "https://code.earthengine.google.com/tasks")
        return
    b_done, b_total = submit_tier1()
    print(f"phase B (tier-1 exports): {b_done}/{b_total} assets ready")
    if b_done < b_total:
        print("-> tier-1 exports running in GEE's cloud; rerun later to collect.")
        return
    collect()


if __name__ == "__main__":
    main()
