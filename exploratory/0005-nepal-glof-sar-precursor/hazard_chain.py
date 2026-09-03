"""0005 step 12 — static hazard-chain factors per facet (consequence triage).

Detection stays exhaustive; these factors only rank ATTENTION. Three per-facet
statics, all first-party GEE data, computed once per facet layer:

  drop_m    available fall height: facet crown elevation minus the lowest
            terrain within 5 km — the first-order control on runout energy
            (Langtang: ~1200 m of fall fluidised the detachment).
  lake_pct  max JRC Global Surface Water occurrence (%) within 10 km at
            elevations below the facet — a standing-water body under the face
            is the avalanche->displacement-wave->outburst cascade multiplier.
  pop_50k   GHSL 2025 population within 50 km at elevations at least 1000 m
            below the facet crown — who lives in the valleys a runout/flood
            would reach.

These are screening PROXIES (radius buffers, not flow-path tracing) and are
labelled as such on the dashboard. chain 0-100 = mean of the three factors'
percentile ranks across the facet layer.

Run: uv run --group etl --with earthengine-api,geopandas python \
       exploratory/0005-nepal-glof-sar-precursor/hazard_chain.py [facets.geojson]
"""
from __future__ import annotations

import csv
import os
import sys
import time

import ee

from extract import init_ee

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
BATCH = 100


def main(facet_path: str) -> None:
    import geopandas as gpd

    init_ee()
    facets = gpd.read_file(facet_path)
    name = os.path.basename(facet_path).replace("facets_", "").replace("_final.geojson", "")
    dst = os.path.join(DATA, f"hazard_chain_{name}.csv")

    coll = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM")
    dem = coll.mosaic().setDefaultProjection(coll.first().projection())
    gsw = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
    pop = ee.ImageCollection("JRC/GHSL/P2023A/GHS_POP").filter(
        ee.Filter.eq("system:index", "2025")).first()

    def per_facet(f):
        geom = f.geometry()
        crown = ee.Number(dem.reduceRegion(ee.Reducer.max(), geom, 30,
                                           bestEffort=True).get("DEM"))
        near5 = geom.buffer(5000)
        floor = ee.Number(dem.reduceRegion(ee.Reducer.min(), near5, 90,
                                           bestEffort=True).get("DEM"))
        near10 = geom.buffer(10000)
        below = dem.lt(crown)
        lake = ee.Number(gsw.updateMask(below).reduceRegion(
            ee.Reducer.max(), near10, 60, bestEffort=True).get("occurrence"))
        near50 = geom.buffer(50000)
        valley = dem.lt(crown.subtract(1000))
        p = ee.Number(pop.updateMask(valley).reduceRegion(
            ee.Reducer.sum(), near50, 250, bestEffort=True).get("population_count"))
        return f.set({"drop_m": crown.subtract(floor), "lake_pct": lake, "pop_50k": p})

    with open(dst, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["facet_id", "drop_m", "lake_pct", "pop_50k"])
        for b0 in range(0, len(facets), BATCH):
            sub = facets.iloc[b0:b0 + BATCH]
            fc = ee.FeatureCollection([
                ee.Feature(ee.Geometry(g.__geo_interface__), {"facet_id": fid})
                for g, fid in zip(sub.geometry, sub.facet_id)
            ]).map(per_facet)
            for attempt in range(5):
                try:
                    got = fc.getInfo()["features"]
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == 4:
                        raise RuntimeError(f"batch {b0}: {e}") from e
                    time.sleep(20 * (attempt + 1))
            for r in got:
                p = r["properties"]
                w.writerow([p["facet_id"], round(p.get("drop_m") or 0),
                            round(p.get("lake_pct") or 0),
                            round(p.get("pop_50k") or 0)])
            print(f"batch {b0}: {len(got)}", flush=True)
    print(f"-> {dst}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else os.path.join(DATA, "facets_langtang_final.geojson"))
