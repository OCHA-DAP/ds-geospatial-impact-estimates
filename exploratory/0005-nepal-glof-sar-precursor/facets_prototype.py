"""0005 step 7 — facet-enumeration prototype: compute the monitoring units,
don't curate them.

The false-alarm study measured glacier-level rates (wrong unit — dilution) with
a hand-drawn box as the positive control (doesn't scale). This prototype builds
the operational unit for the Langtang test region and asks the question that
gates everything else: does the AUTO-GENERATED facet containing the detachment
still catch the collapse?

Recipe (monitoring_design.md §1):
  ice mask   = GLIMS boundaries (deduped per glac_id) + 200 m headwall buffer
  ∩ slope    >= 25 deg (GLO30)
  ∩ elev     >= 4800 m
  split by dominant aspect octant (N/NE/E/.../NW), connected components at 30 m,
  drop < 0.5 km2, grid-split any component > 4 km2 (~2 km tiles).

Outputs: data/facets_langtang.geojson + size/aspect stats + the facet covering
the detachment scar centroid (28.28648N 85.52284E), then the detector replay on
that facet (same machinery as falsealarms: leave-one-out climatology minus the
same-date facet-fleet median, worst 3-consecutive over Jun 1 - Aug 25).

Run: uv run --group etl --with earthengine-api,geopandas python \
       exploratory/0005-nepal-glof-sar-precursor/facets_prototype.py
"""
from __future__ import annotations

import csv
import json
import os
import time

import ee

from extract import init_ee, s1

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

REGION = [84.9, 27.9, 86.3, 28.7]  # same test region as the false-alarm study
# pixel-level criteria: the elevation floor is deliberately lower than the
# fleet study's glacier-MEAN floor (4800) — a face spans 4500-6500 m and the
# Langtang scar centroid sits at 4704 m
SLOPE_MIN, ELEV_MIN = 25, 4500
MIN_KM2, MAX_KM2 = 0.5, 4.0
SCAR = (85.52284, 28.28648)  # Langtang detachment centroid from analysis.py
EVENT_YEAR = 2026
TS_START = "2020-01-01"
RUN_LEN, ALARM_Z, DOY_WIN, MIN_POOL = 3, -2.0, 12, 10
SEASON = (152, 237)  # Jun 1 - Aug 25


def enumerate_facets() -> str:
    """Label the steep-ice mask by aspect octant, vectorize, return geojson path."""
    dst = os.path.join(DATA, "facets_langtang.geojson")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        print("facets exist, skipped enumeration")
        return dst
    region = ee.Geometry.Rectangle(REGION)
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

    ice = ee.Image(0).byte().paint(g, 1)
    # 200 m headwall buffer: hanging ice and icy headwalls sit just above the
    # inventory boundary (Langtang itself detached partly above the polygon)
    ice_buf = ice.focalMax(radius=200, units="meters")
    # per-pixel aspect at 30 m is noisy — one face shatters into thousands of
    # octant slivers (this is what blew GEE's 5000-element vectorization cap).
    # Smooth it with a 300 m circular mean (via sin/cos to handle the 0/360
    # wrap) so octant regions are coherent before labelling.
    import math

    rad = aspect.multiply(math.pi / 180)
    sy = rad.sin().focalMean(300, "circle", "meters")
    cx = rad.cos().focalMean(300, "circle", "meters")
    smooth_deg = sy.atan2(cx).multiply(180 / math.pi).add(360).mod(360)
    octant = smooth_deg.add(22.5).divide(45).floor().mod(8).add(1).byte()  # 1..8, N first
    mask = ice_buf.eq(1).And(slope.gte(SLOPE_MIN)).And(dem.gte(ELEV_MIN))
    # drop sub-0.25 km2 label patches server-side (0.25 km2 at 30 m ~ 278 px);
    # the client-side 0.5 km2 floor still applies after grid-splitting
    labeled = octant.updateMask(mask).rename("aspect8")
    big = labeled.connectedPixelCount(300, True).gte(278)
    labeled = labeled.updateMask(big)

    # vectorize one octant at a time — keeps each query far from the cap
    feats = []
    for o in range(1, 9):
        fc = labeled.updateMask(labeled.eq(o)).reduceToVectors(
            geometry=region, scale=30, geometryType="polygon", eightConnected=True,
            labelProperty="aspect8", maxPixels=1e10, bestEffort=False,
        )
        got = fc.getInfo()["features"]
        feats.extend(got)
        print(f"octant {o}: {len(got)} components", flush=True)
    with open(dst, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    print(f"raw components: {len(feats)} -> {dst}")
    return dst


def shape_facets(path: str):
    """Client-side size enforcement: drop slivers, grid-split monsters."""
    import geopandas as gpd
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
        step = 2000  # 2 km grid split
        minx, miny, maxx, maxy = r.geometry.bounds
        x = minx
        while x < maxx:
            y = miny
            while y < maxy:
                t = r.geometry.intersection(sbox(x, y, x + step, y + step))
                if not t.is_empty and t.area / 1e6 >= MIN_KM2 / 2:
                    out.append((t, int(r.aspect8)))
                y += step
            x += step
    import pandas as pd

    facets = gpd.GeoDataFrame(
        pd.DataFrame({"aspect8": [a for _, a in out]}),
        geometry=[g for g, _ in out], crs=32645,
    ).to_crs(4326)
    facets["facet_id"] = [f"F{i:05d}" for i in range(len(facets))]
    facets["km2"] = facets.to_crs(32645).geometry.area / 1e6
    aspects = "N NE E SE S SW W NW".split()
    facets["aspect"] = facets.aspect8.map(lambda a: aspects[a - 1])
    dst = os.path.join(DATA, "facets_langtang_final.geojson")
    facets.to_file(dst, driver="GeoJSON")
    print(f"facets: {len(facets)} (median {facets.km2.median():.2f} km2, "
          f"total {facets.km2.sum():.0f} km2)")
    print("by aspect:", facets.groupby("aspect").size().to_dict())
    # gate: the facet that best overlaps the detachment box (the scar CENTROID
    # is biased downslope — mid-fall debris, not the crown — so point-in-polygon
    # is the wrong test)
    from shapely.geometry import box as sbox

    src = sbox(85.512, 28.269, 85.533, 28.293)  # analysis.py SOURCE_BOX
    inter = facets.geometry.intersection(src)
    facets["src_overlap_km2"] = (
        gpd.GeoSeries(inter, crs=4326).to_crs(32645).area / 1e6
    )
    hit = facets[facets.src_overlap_km2 > 0.1].sort_values(
        "src_overlap_km2", ascending=False)
    if hit.empty:
        raise RuntimeError("no facet overlaps the detachment box by >0.1 km2 — "
                           "mask criteria exclude the source zone")
    hrow = hit.iloc[0]
    print(f"facets overlapping the detachment box: {len(hit)}; best: "
          f"{hrow.facet_id} ({hrow.km2:.2f} km2, aspect {hrow.aspect}, "
          f"overlap {hrow.src_overlap_km2:.2f} km2)")
    return facets, hrow.facet_id


def extract_and_replay(facets, target_id: str) -> None:
    """Detector on the detachment facet, with a same-aspect facet sample as the
    fleet control (30 facets keeps the extraction quick)."""
    import numpy as np
    import pandas as pd

    target = facets[facets.facet_id == target_id]
    fleet = facets[(facets.facet_id != target_id)].sample(
        n=min(30, len(facets) - 1), random_state=0
    )
    sel = pd.concat([target, fleet])
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry(g.__geo_interface__), {"facet_id": fid})
        for g, fid in zip(sel.geometry, sel.facet_id)
    ])
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    bounds = fc.geometry().bounds()

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

    dst = os.path.join(DATA, "facet_ts_langtang.csv")
    if not (os.path.exists(dst) and os.path.getsize(dst) > 0):
        with open(dst, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["t", "orbit", "facet_id", "vv_db", "n_pix"])
            for year in range(int(TS_START[:4]), 2027):
                col = (s1().filterBounds(bounds)
                       .filterDate(f"{year}-01-01", min(f"{year + 1}-01-01", "2026-08-26"))
                       .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING")))
                fcoll = ee.FeatureCollection(col.map(per_image)).flatten().filter(
                    ee.Filter.notNull(["vv_db"]))
                for attempt in range(4):
                    try:
                        got = fcoll.getInfo()["features"]
                        break
                    except Exception as e:  # noqa: BLE001
                        if attempt == 3:
                            raise RuntimeError(f"{year}: {e}") from e
                        time.sleep(15 * (attempt + 1))
                for r in got:
                    p = r["properties"]
                    w.writerow([p["t"], p["orbit"], p["facet_id"], p["vv_db"], p["n_pix"]])
                print(f"{year}: +{len(got)} rows", flush=True)

    df = pd.read_csv(dst, parse_dates=["t"])
    full = df.groupby(["facet_id", "orbit"])["n_pix"].transform("max")
    df = df[(df.n_pix >= 0.8 * full) & df.vv_db.notna()].copy()
    df["year"], df["doy"], df["date"] = df.t.dt.year, df.t.dt.dayofyear, df.t.dt.date
    out = []
    for (fid, orbit), g in df.groupby(["facet_id", "orbit"]):
        v = g.sort_values("t").reset_index(drop=True)
        doy, yr, vv = v.doy.values, v.year.values, v.vv_db.values
        z = np.full(len(v), np.nan)
        for i in range(len(v)):
            dd = np.minimum(np.abs(doy - doy[i]), 365 - np.abs(doy - doy[i]))
            pool = (dd <= DOY_WIN) & (yr != yr[i])
            if pool.sum() >= MIN_POOL:
                z[i] = (vv[i] - vv[pool].mean()) / vv[pool].std(ddof=1)
        v["z"] = z
        out.append(v)
    zdf = pd.concat(out, ignore_index=True).dropna(subset=["z"])
    med = zdf[zdf.facet_id != target_id].groupby(["orbit", "date"]).z.agg(["median", "size"])
    zdf = zdf.join(med, on=["orbit", "date"])
    zdf = zdf[zdf["size"] >= 8].copy()
    zdf["z_adj"] = zdf.z - zdf["median"]
    seas = zdf[(zdf.doy >= SEASON[0]) & (zdf.doy <= SEASON[1])]
    rows = []
    for (fid, year, orbit), g in seas.groupby(["facet_id", "year", "orbit"]):
        v = g.sort_values("t").z_adj.values
        if len(v) >= RUN_LEN:
            rows.append({"facet_id": fid, "year": year,
                         "stat": min(max(v[i:i + RUN_LEN]) for i in range(len(v) - RUN_LEN + 1))})
    res = pd.DataFrame(rows).groupby(["facet_id", "year"]).stat.min().reset_index()
    tgt = res[res.facet_id == target_id].sort_values("year")
    print("\n== detachment facet, worst 3-run z_adj per year ==")
    print("  ".join(f"{int(r.year)}:{r.stat:+.1f}" for r in tgt.itertuples()))
    ev = tgt[tgt.year == EVENT_YEAR]
    if ev.empty:
        print("event year not testable on the facet")
    else:
        s = float(ev.stat.iloc[0])
        print(f"2026 (collapse season): {s:+.2f} -> "
              f"{'CAUGHT' if s <= ALARM_Z else 'missed'} at {ALARM_Z}")
    fl = res[res.facet_id != target_id]
    print(f"facet-fleet context: {int((fl.stat <= ALARM_Z).sum())}/{len(fl)} "
          f"facet-seasons alarm ({100 * (fl.stat <= ALARM_Z).mean():.1f}%)")


if __name__ == "__main__":
    init_ee()
    facets, target = shape_facets(enumerate_facets())
    extract_and_replay(facets, target)
