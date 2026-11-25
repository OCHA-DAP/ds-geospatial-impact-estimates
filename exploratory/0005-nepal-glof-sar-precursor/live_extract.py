"""0005 step 10a — extraction for the live facet-status map.

Pulls the full descending-orbit VV series (2020-01-01 -> now) for ALL facets in
data/facets_langtang_final.geojson (the 580 computed monitoring units), plus a
hillshade of the region for the dashboard basemap (artifact CSP blocks external
tile servers, so the base ships as an embedded image).

Facets are batched (140 per request) to keep each getInfo payload modest; years
chunked as everywhere else in 0005.

Run: uv run --group etl --with earthengine-api,geopandas python \
       exploratory/0005-nepal-glof-sar-precursor/live_extract.py
"""
from __future__ import annotations

import csv
import os
import time
import urllib.request

import ee

from extract import init_ee, s1

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

REGION = [84.9, 27.9, 86.3, 28.7]
TS_START, TS_END = "2020-01-01", "2026-10-01"
BATCH = 60  # 140 x ~50 scenes/yr blew GEE's 5000-element accumulation cap


def main() -> None:
    import geopandas as gpd

    init_ee()
    facets = gpd.read_file(os.path.join(DATA, "facets_langtang_final.geojson"))
    print(f"{len(facets)} facets")

    hill = os.path.join(DATA, "live_hillshade.tif")
    if not os.path.exists(hill):
        coll = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM")
        dem = coll.mosaic().setDefaultProjection(coll.first().projection())
        img = ee.Terrain.hillshade(dem, 315, 40).toFloat()
        url = img.getDownloadURL({"scale": 120, "region": ee.Geometry.Rectangle(REGION),
                                  "format": "GEO_TIFF", "crs": "EPSG:4326"})
        urllib.request.urlretrieve(url, hill)
        print(f"hillshade -> {hill} ({os.path.getsize(hill) / 1e6:.1f} MB)")

    dst = os.path.join(DATA, "live_facet_ts.csv")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        print("live series exists, skipped")
        return
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    batches = []
    for b0 in range(0, len(facets), BATCH):
        sub = facets.iloc[b0:b0 + BATCH]
        batches.append(ee.FeatureCollection([
            ee.Feature(ee.Geometry(g.__geo_interface__), {"facet_id": fid})
            for g, fid in zip(sub.geometry, sub.facet_id)
        ]))
    rows = 0
    with open(dst, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t", "orbit", "facet_id", "vv_db", "n_pix"])
        for year in range(int(TS_START[:4]), int(TS_END[:4]) + 1):
            y1 = min(f"{year + 1}-01-01", TS_END)
            for bi, fc in enumerate(batches):
                col = (s1().filterBounds(fc.geometry().bounds())
                       .filterDate(f"{year}-01-01", y1)
                       .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING")))

                def per_image(img):
                    return img.reduceRegions(fc, reducer, 30).map(
                        lambda f: ee.Feature(None, {
                            "t": img.date().format("YYYY-MM-dd'T'HH:mm"),
                            "orbit": img.get("relativeOrbitNumber_start"),
                            "facet_id": f.get("facet_id"),
                            "vv_db": f.get("VV_mean"),
                            "n_pix": f.get("VV_count"),
                        })
                    )

                fcoll = ee.FeatureCollection(col.map(per_image)).flatten().filter(
                    ee.Filter.notNull(["vv_db"]))
                for attempt in range(5):
                    try:
                        got = fcoll.getInfo()["features"]
                        break
                    except Exception as e:  # noqa: BLE001
                        if attempt == 4:
                            raise RuntimeError(f"{year} batch {bi}: {e}") from e
                        time.sleep(20 * (attempt + 1))
                for r in got:
                    p = r["properties"]
                    w.writerow([p["t"], p["orbit"], p["facet_id"], p["vv_db"], p["n_pix"]])
                rows += len(got)
                print(f"{year} b{bi}: +{len(got)} (total {rows})", flush=True)
    print(f"-> {dst}")


if __name__ == "__main__":
    main()
