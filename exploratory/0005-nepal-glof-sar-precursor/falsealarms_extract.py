"""0005 step 3 — fleet extraction for the false-alarm study.

Question (raised on review of the precursor finding): if the morning-pass
divergence detector had been running prospectively, how often would it have
fired on faces that did NOT collapse? This script samples every 'Langtang-like'
glacier face in the surrounding ~130x90 km of the Nepal Himalaya and pulls the
same per-orbit Sentinel-1 VV/VH series used in extract.py. falsealarms_analysis.py
then replays the detector over every face-season.

Face selection (GLIMS 20230607, deduped to one boundary per glac_id):
  glacier boundary polygons, 0.5-15 km2, mean elevation >= 4800 m, and
  GLO30 mean slope >= 25 deg (hanging-glacier geometry, like the source face).
  Faces intersecting the source box are flagged is_source=1, kept as the
  positive control the detector must catch.

Output: data/fleet_faces.csv (metadata) + data/fleet_timeseries.csv
(t, orbit, pass, face_id, vv_db, vh_db, n_pix). Scale 30 m — box means over
>=0.5 km2 are insensitive to 10 vs 30 m, and it is 9x less compute.

Run: uv run --group etl --with earthengine-api python \
       exploratory/0005-nepal-glof-sar-precursor/falsealarms_extract.py
"""
from __future__ import annotations

import csv
import os
import time

import ee

from extract import AOIS, init_ee, s1

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

REGION = [84.9, 27.9, 86.3, 28.7]
MIN_KM2, MAX_KM2 = 0.5, 15.0
MIN_ELEV, MIN_SLOPE = 4800, 25
MAX_FACES = 45
TS_START, TS_END = "2020-01-01", "2026-08-26"  # stop at the event
SCALE = 30


def select_faces() -> ee.FeatureCollection:
    region = ee.Geometry.Rectangle(REGION)
    g = (
        ee.FeatureCollection("GLIMS/20230607")
        .filterBounds(region)
        .filter(ee.Filter.eq("line_type", "glac_bound"))
        .filter(ee.Filter.rangeContains("db_area", MIN_KM2, MAX_KM2))
        .filter(ee.Filter.gte("mean_elev", MIN_ELEV))
    )
    # GLIMS carries multiple analyses per glacier — keep the latest per glac_id
    latest = g.reduceColumns(
        ee.Reducer.max().group(groupField=1, groupName="glac_id"),
        ["anlys_id", "glac_id"],
    ).get("groups")
    ids = ee.List(latest).map(lambda d: ee.Dictionary(d).get("max"))
    g = g.filter(ee.Filter.inList("anlys_id", ids))

    coll = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM")
    dem = coll.mosaic().setDefaultProjection(coll.first().projection())
    slope = ee.Terrain.slope(dem)
    g = slope.reduceRegions(g, ee.Reducer.mean(), 30).filter(
        ee.Filter.gte("mean", MIN_SLOPE)
    )
    src_box = ee.Geometry.Rectangle(AOIS["source"])
    g = g.map(
        lambda f: f.set(
            {
                "is_source": f.geometry().intersects(src_box, 100),
                "face_id": f.get("glac_id"),
                "slope_deg": f.get("mean"),
            }
        )
    )
    return g.limit(MAX_FACES, "db_area", False)


def main() -> None:
    init_ee()
    faces = select_faces()
    meta = faces.getInfo()["features"]
    if not meta:
        raise RuntimeError("face selection returned nothing — check GLIMS filters")
    print(f"{len(meta)} faces selected "
          f"({sum(bool(f['properties']['is_source']) for f in meta)} overlap the source box)")
    with open(os.path.join(DATA, "fleet_faces.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["face_id", "name", "area_km2", "mean_elev", "slope_deg", "is_source"])
        for f in meta:
            p = f["properties"]
            w.writerow([p["face_id"], p.get("glac_name") or "", p["db_area"],
                        p["mean_elev"], round(p["slope_deg"], 1), int(bool(p["is_source"]))])

    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    bounds = faces.geometry().bounds()

    def per_image(img):
        return img.reduceRegions(faces, reducer, SCALE).map(
            lambda f: ee.Feature(
                None,
                {
                    "t": img.date().format("YYYY-MM-dd'T'HH:mm"),
                    "orbit": img.get("relativeOrbitNumber_start"),
                    "pass": img.get("orbitProperties_pass"),
                    "face_id": f.get("face_id"),
                    "vv_db": f.get("VV_mean"),
                    "vh_db": f.get("VH_mean"),
                    "n_pix": f.get("VV_count"),
                },
            )
        )

    dst = os.path.join(DATA, "fleet_timeseries.csv")
    rows = 0
    with open(dst, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t", "orbit", "pass", "face_id", "vv_db", "vh_db", "n_pix"])
        year = int(TS_START[:4])
        quarters = [(f"{y}-{m:02d}-01", f"{y + (m + 3 > 12)}-{(m + 2) % 12 + 1:02d}-01")
                    for y in range(year, 2027) for m in (1, 4, 7, 10)]
        for q0, q1 in quarters:
            if q0 >= TS_END:
                break
            q1 = min(q1, TS_END)
            col = s1().filterBounds(bounds).filterDate(q0, q1)
            fc = ee.FeatureCollection(col.map(per_image)).flatten().filter(
                ee.Filter.notNull(["vv_db"])
            )
            for attempt in range(4):
                try:
                    got = fc.getInfo()["features"]
                    break
                except Exception as e:  # noqa: BLE001 — 429s; retried, then re-raised
                    if attempt == 3:
                        raise RuntimeError(f"quarter {q0} failed after 4 tries: {e}") from e
                    time.sleep(15 * (attempt + 1))
            for r in got:
                p = r["properties"]
                w.writerow([p["t"], p["orbit"], p["pass"], p["face_id"],
                            p["vv_db"], p["vh_db"], p["n_pix"]])
            rows += len(got)
            print(f"{q0}: +{len(got)} rows (total {rows})", flush=True)
    print(f"fleet timeseries -> {dst}")


if __name__ == "__main__":
    main()
