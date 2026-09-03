"""0005 step 14 — downstream basin chains: connect face risk to people visually.

No routing needed: HydroBASINS level-10 polygons carry NEXT_DOWN pointers, so
"downstream of a face" is a client-side graph walk over basin ids. Population
per basin comes from GHSL. The dashboard then draws, for any selected face, the
chain of downstream basins as a ribbon labelled with population — a cascade
corridor at basin scale, explicitly not an inundation model.

Output: data/basins_himalaya.json
  {"basins": {id: {"next": id|0, "pop": int, "poly": [[lon,lat],...]}},
   "facet_basin": {facet_id: basin_id}}

Run: uv run --group etl --with earthengine-api,geopandas python \
       exploratory/0005-nepal-glof-sar-precursor/downstream_build.py
"""
from __future__ import annotations

import json
import os
import time

import ee

from extract import init_ee
from himalaya_batch import DOMAIN

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
LEVEL = "hybas_10"
POP_BATCH = 200


def main() -> None:
    import geopandas as gpd

    init_ee()
    dst = os.path.join(DATA, "basins_himalaya.json")
    region = ee.Geometry.Rectangle(DOMAIN)
    fc = (ee.FeatureCollection(f"WWF/HydroSHEDS/v1/Basins/{LEVEL}")
          .filterBounds(region)
          .map(lambda f: ee.Feature(f.geometry().simplify(400),
                                    {"HYBAS_ID": f.get("HYBAS_ID"),
                                     "NEXT_DOWN": f.get("NEXT_DOWN")})))
    n = fc.size().getInfo()
    print(f"{n} level-10 basins in domain")
    feats = []
    lst = fc.toList(n)
    for off in range(0, n, 400):
        for attempt in range(4):
            try:
                feats.extend(ee.FeatureCollection(lst.slice(off, off + 400))
                             .getInfo()["features"])
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    raise RuntimeError(f"basin chunk {off}: {e}") from e
                time.sleep(15 * (attempt + 1))
        print(f"  {len(feats)}/{n}", flush=True)

    pop = ee.ImageCollection("JRC/GHSL/P2023A/GHS_POP").filter(
        ee.Filter.eq("system:index", "2025")).first()
    # two exposure figures per basin: total, and near-channel — population
    # within ~1 km of a river channel (MERIT-Hydro upstream area >= 50 km2),
    # which is what a debris flow / flood wave can actually reach
    upa = ee.Image("MERIT/Hydro/v1_0_1").select("upa")
    channel = upa.gte(50).selfMask().focalMax(1000, "circle", "meters")
    both = (pop.rename("pop_all")
            .addBands(pop.updateMask(channel).unmask(0).rename("pop_ch")))
    pops, pops_ch = {}, {}
    for off in range(0, n, POP_BATCH):
        sub = ee.FeatureCollection([
            ee.Feature(ee.Geometry(f["geometry"]), {"HYBAS_ID": f["properties"]["HYBAS_ID"]})
            for f in feats[off:off + POP_BATCH]
        ])
        rr = both.reduceRegions(sub, ee.Reducer.sum(), 250)
        for attempt in range(4):
            try:
                got = rr.getInfo()["features"]
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    raise RuntimeError(f"pop chunk {off}: {e}") from e
                time.sleep(15 * (attempt + 1))
        for r in got:
            p = r["properties"]
            pops[p["HYBAS_ID"]] = int(p.get("pop_all") or 0)
            pops_ch[p["HYBAS_ID"]] = int(p.get("pop_ch") or 0)
        print(f"  pop {off + len(got)}/{n}", flush=True)

    gdf = gpd.GeoDataFrame.from_features(feats, crs=4326)
    facets = gpd.read_file(os.path.join(DATA, "facets_himalaya_final.geojson"))
    pts = facets.copy()
    pts.geometry = pts.geometry.representative_point()
    joined = gpd.sjoin(pts[["facet_id", "geometry"]], gdf[["HYBAS_ID", "geometry"]],
                       how="left", predicate="within")
    facet_basin = {r.facet_id: int(r.HYBAS_ID) for r in joined.itertuples()
                   if r.HYBAS_ID == r.HYBAS_ID}

    basins = {}
    # largest exterior ring per basin, coordinates rounded for payload size
    for row in gdf.itertuples():
        g = max(getattr(row.geometry, "geoms", [row.geometry]), key=lambda x: x.area)
        basins[int(row.HYBAS_ID)] = {
            "next": int(row.NEXT_DOWN),
            "pop": pops.get(row.HYBAS_ID, 0),
            "popc": pops_ch.get(row.HYBAS_ID, 0),
            "poly": [[round(x, 3), round(y, 3)] for x, y in g.exterior.coords],
        }
    with open(dst, "w") as f:
        json.dump({"basins": basins, "facet_basin": facet_basin},
                  f, separators=(",", ":"))
    print(f"{os.path.getsize(dst) / 1e6:.1f} MB -> {dst} "
          f"({len(facet_basin)} facets mapped to basins)")


if __name__ == "__main__":
    main()
