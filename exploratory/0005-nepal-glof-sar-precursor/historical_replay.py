"""0005 step 6 — Phase-0 historical replay: does the morning-pass melt detector
catch the known S1-era glacier detachments?

Events (all with published source coordinates at basin precision):
  aru1       2016-07-17  Aru Range, Tibet (Kaab et al. 2018)  — melt-driven, expect catch
  aru2       2016-09-21  Aru Range, Tibet, twin of aru1        — melt-driven, expect catch
  sedongpu   2018-10-16  Sedongpu basin, SE Tibet              — melt/thaw-driven, expect catch
  chamoli    2021-02-07  Ronti Gad, Uttarakhand                — WINTER failure, predicted MISS
  marmolada  2022-07-03  Punta Rocca serac, Alps               — heatwave-driven, best analogue

Per event:
  1. Locate the actual detachment from the data: post-event scenes vs a pre-event
     stack on one descending orbit -> |z| map over a search box; the largest
     |z|>=3 cluster centroid becomes the detector-box centre (2.4 km box). If no
     cluster (Marmolada's serac was ~64e3 m3, likely sub-resolution), fall back
     to the published point.
  2. Fleet for the regional control: GLIMS faces near the event (same criteria
     family as falsealarms_extract, elevation floor per region), up to 25.
  3. Detector replay on PRE-EVENT data only (series truncated at the event):
     per face x descending orbit, leave-one-out climatology z (+/-12 d DOY,
     >=10-acq pool), minus the same-date fleet-median z; statistic = the worst
     3-consecutive-acquisition value inside the 90 days before the event (and,
     for context, the same window in every other year). Alarm at <= -2.

Caveat carried into the writeup: for the source box the leave-one-out baseline
includes post-collapse years (pre-event-only baselines are too thin for the
2016 events); the collapsed surface differs, which can bias those tests either
way. The fleet is unaffected.

Run: uv run --group etl --with earthengine-api,rasterio,scipy python \
       exploratory/0005-nepal-glof-sar-precursor/historical_replay.py
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import time

import ee
import numpy as np

from extract import init_ee, s1, zscore, download

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

TS_START = "2015-01-01"
BOX_HALF = 0.011  # detector box half-size in degrees (~2.4 km)
SEARCH_HALF = 0.06  # scar search box half-size
WINDOW_DAYS = 90
RUN_LEN, ALARM_Z, DOY_WIN, MIN_POOL, MIN_FACE_DATE = 3, -2.0, 12, 10, 6

TS_END = "2025-01-01"  # series run PAST each event: 2015-16 Tibet has almost no
# S1, so leave-one-out baselines need later years; the source box's baseline then
# contains post-collapse surface — carried as a caveat in the writeup.

EVENTS = {
    # name: (lon, lat, event date, scar pre-window start, elev floor,
    #        fleet slope min, fleet area min, fleet box half-deg, use scar step,
    #        expectation)
    "aru1": (82.24, 34.02, "2016-07-17", "2016-04-15", 5000, 25, 0.5, 0.35, True,
             "melt-driven: expect catch (S1 archive may be too thin in 2016)"),
    "aru2": (82.22, 33.98, "2016-09-21", "2016-06-20", 5000, 25, 0.5, 0.35, True,
             "melt-driven: expect catch (S1 archive may be too thin in 2016)"),
    "sedongpu": (94.92, 29.81, "2018-10-16", "2018-07-15", 4200, 25, 0.5, 0.35, True,
                 "melt/thaw: expect catch"),
    "chamoli": (79.732, 30.373, "2021-02-07", "2020-11-01", 4800, 25, 0.5, 0.35, True,
                "winter failure: predicted miss"),
    # the Marmolada serac (~64e3 m3) is sub-resolution for a GRD scar map: use the
    # published point, and relax the fleet criteria for the smaller Alpine glaciers
    "marmolada": (11.852, 46.437, "2022-07-03", "2022-04-01", 2500, 20, 0.2, 0.6, False,
                  "heatwave serac: best analogue"),
}


def locate_scar(name: str, lon: float, lat: float, event: str, pre_start: str):
    """Largest post-event |z|>=3 cluster centroid inside the search box, or the
    published point if the change is sub-resolution (reported as such)."""
    import rasterio
    import rasterio.warp
    from scipy import ndimage

    box = [lon - SEARCH_HALF * 1.25, lat - SEARCH_HALF, lon + SEARCH_HALF * 1.25, lat + SEARCH_HALF]
    rect = ee.Geometry.Rectangle(box)
    ev = dt.date.fromisoformat(event)
    post0, post1 = str(ev + dt.timedelta(days=1)), str(ev + dt.timedelta(days=45))
    # any pass works for LOCATING the scar (the morning-pass constraint applies to
    # the detector, not to change mapping)
    col = s1().filterBounds(rect)
    post = col.filterDate(post0, post1)
    orbits = post.aggregate_array("relativeOrbitNumber_start").getInfo()
    if not orbits:
        print(f"{name}: no post-event scene at all in {post0}..{post1} — using published point")
        return lon, lat, False
    orbit = max(set(orbits), key=orbits.count)
    oc = col.filter(ee.Filter.eq("relativeOrbitNumber_start", orbit))
    pre = oc.filterDate(pre_start, event)
    if pre.size().getInfo() < 4:
        print(f"{name}: <4 pre scenes on orbit {orbit} — using published point")
        return lon, lat, False
    dst = os.path.join(DATA, f"hist_scar_{name}.tif")
    download(zscore(oc.filterDate(post0, post1).mean(), pre), box, dst)
    with rasterio.open(dst) as src:
        z = src.read(1)
        mask = np.abs(z) >= 3
        lab, n = ndimage.label(mask)
        if n == 0:
            print(f"{name}: no |z|>=3 pixels (orbit {orbit}) — using published point")
            return lon, lat, False
        # candidate clusters: >=50 px AND centroid within 5 km of the published
        # point — the largest change in the box is often the runout/deposit
        # (Sedongpu's biggest cluster is the river blockage 6 km downstream)
        sizes = np.bincount(lab.ravel())[1:]
        best, best_size = None, 0
        for ci in np.argsort(sizes)[::-1][:20]:
            if sizes[ci] < 50:
                break
            rr, cc = np.nonzero(lab == ci + 1)
            xs, ys = rasterio.transform.xy(src.transform, rr, cc)
            glon, glat = rasterio.warp.transform(src.crs, "EPSG:4326",
                                                 [float(np.mean(xs))], [float(np.mean(ys))])
            dkm = np.hypot((glon[0] - lon) * 111 * np.cos(np.radians(lat)),
                           (glat[0] - lat) * 111)
            if dkm <= 5 and sizes[ci] > best_size:
                best, best_size = (glon[0], glat[0]), sizes[ci]
        if best is None:
            print(f"{name}: no scar cluster within 5 km (orbit {orbit}) — using published point")
            return lon, lat, False
        px_km2 = abs(src.transform.a * src.transform.e) / 1e6
        dkm = np.hypot((best[0] - lon) * 111 * np.cos(np.radians(lat)), (best[1] - lat) * 111)
        print(f"{name}: scar cluster {best_size * px_km2:.2f} km2 at "
              f"{best[1]:.4f}N {best[0]:.4f}E (orbit {orbit}, {dkm:.1f} km from published)")
        return best[0], best[1], True


def fleet_faces(lon: float, lat: float, elev_min: float, src_box: list[float],
                slope_min: float = 25, area_min: float = 0.5, box_half: float = 0.35):
    region = ee.Geometry.Rectangle([lon - box_half, lat - box_half * 0.85,
                                    lon + box_half, lat + box_half * 0.85])
    g = (
        ee.FeatureCollection("GLIMS/20230607")
        .filterBounds(region)
        .filter(ee.Filter.eq("line_type", "glac_bound"))
        .filter(ee.Filter.rangeContains("db_area", area_min, 15.0))
        .filter(ee.Filter.gte("mean_elev", elev_min))
    )
    latest = g.reduceColumns(
        ee.Reducer.max().group(groupField=1, groupName="glac_id"), ["anlys_id", "glac_id"]
    ).get("groups")
    ids = ee.List(latest).map(lambda d: ee.Dictionary(d).get("max"))
    g = g.filter(ee.Filter.inList("anlys_id", ids))
    coll = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM")
    dem = coll.mosaic().setDefaultProjection(coll.first().projection())
    g = ee.Terrain.slope(dem).reduceRegions(g, ee.Reducer.mean(), 30).filter(
        ee.Filter.gte("mean", slope_min)
    )
    sb = ee.Geometry.Rectangle(src_box)
    g = g.map(lambda f: f.set("face_id", f.get("glac_id"))
              .set("touches_src", f.geometry().intersects(sb, 100)))
    g = g.filter(ee.Filter.eq("touches_src", False))
    return g.limit(25, "db_area", False)


def extract_series(name: str, faces, src_box: list[float]) -> str:
    dst = os.path.join(DATA, f"hist_ts_{name}.csv")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        print(f"{name}: series exists, skipped")
        return dst
    fc = faces.merge(ee.FeatureCollection([
        ee.Feature(ee.Geometry.Rectangle(src_box), {"face_id": "SOURCE-BOX"})
    ]))
    n_faces = fc.size().getInfo()
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    bounds = fc.geometry().bounds()

    def per_image(img):
        return img.reduceRegions(fc, reducer, 30).map(
            lambda f: ee.Feature(None, {
                "t": img.date().format("YYYY-MM-dd'T'HH:mm"),
                "orbit": img.get("relativeOrbitNumber_start"),
                "face_id": f.get("face_id"),
                "vv_db": f.get("VV_mean"),
                "n_pix": f.get("VV_count"),
            })
        )

    rows = 0
    with open(dst, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t", "orbit", "face_id", "vv_db", "n_pix"])
        year0 = int(TS_START[:4])
        for year in range(year0, int(TS_END[:4])):
            col = (s1().filterBounds(bounds).filterDate(f"{year}-01-01", f"{year + 1}-01-01")
                   .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING")))
            fcoll = ee.FeatureCollection(col.map(per_image)).flatten().filter(
                ee.Filter.notNull(["vv_db"]))
            for attempt in range(4):
                try:
                    got = fcoll.getInfo()["features"]
                    break
                except Exception as e:  # noqa: BLE001 — 429s; retried then re-raised
                    if attempt == 3:
                        raise RuntimeError(f"{name} {year}: failed after 4 tries: {e}") from e
                    time.sleep(15 * (attempt + 1))
            for r in got:
                p = r["properties"]
                w.writerow([p["t"], p["orbit"], p["face_id"], p["vv_db"], p["n_pix"]])
            rows += len(got)
        print(f"{name}: {rows} series rows, {n_faces} faces (incl. source box) -> {dst}")
    return dst


def replay(name: str, csv_path: str, event: str, expectation: str) -> dict:
    import pandas as pd

    ev = pd.Timestamp(event)
    df = pd.read_csv(csv_path, parse_dates=["t"])
    full = df.groupby(["face_id", "orbit"])["n_pix"].transform("max")
    df = df[(df.n_pix >= 0.8 * full) & df.vv_db.notna()].copy()
    df["year"] = df.t.dt.year
    df["doy"] = df.t.dt.dayofyear
    df["date"] = df.t.dt.date
    ok = df.groupby(["face_id", "orbit"]).year.transform("nunique") >= 3
    df = df[ok]
    if "SOURCE-BOX" not in set(df.face_id):
        raise RuntimeError(f"{name}: source box has no usable descending series")
    n_fleet_faces = df[df.face_id != "SOURCE-BOX"].face_id.nunique()
    min_face_date = MIN_FACE_DATE if n_fleet_faces >= 10 else max(3, n_fleet_faces // 2)
    src_counts = df[df.face_id == "SOURCE-BOX"].groupby("year").size()
    print(f"{name}: {n_fleet_faces} fleet faces usable, source-box acquisitions/year: "
          + " ".join(f"{y}:{c}" for y, c in src_counts.items()))

    out = []
    for (fid, orbit), g in df.groupby(["face_id", "orbit"]):
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
    med = zdf[zdf.face_id != "SOURCE-BOX"].groupby(["orbit", "date"]).z.agg(["median", "size"])
    zdf = zdf.join(med, on=["orbit", "date"])
    zdf = zdf[zdf["size"] >= min_face_date].copy()
    zdf["z_adj"] = zdf.z - zdf["median"]

    # the 90-day-before-event window, applied to the event year and every other year
    w1 = ev.dayofyear
    w0 = (ev - pd.Timedelta(days=WINDOW_DAYS)).dayofyear
    in_win = ((zdf.doy > w0) & (zdf.doy <= w1)) if w0 < w1 else ((zdf.doy > w0) | (zdf.doy <= w1))
    seas = zdf[in_win]
    if w0 > w1:  # window wraps the new year (chamoli): assign wrap acquisitions to the later year
        seas = seas.copy()
        seas.loc[seas.doy > w0, "year"] += 1

    rows = []
    for (fid, year, orbit), g in seas.groupby(["face_id", "year", "orbit"]):
        v = g.sort_values("t").z_adj.values
        if len(v) < RUN_LEN:
            continue
        stat = min(max(v[i:i + RUN_LEN]) for i in range(len(v) - RUN_LEN + 1))
        rows.append({"face_id": fid, "year": year, "orbit": orbit, "n": len(v), "stat": stat})
    res = pd.DataFrame(rows)
    if res.empty:
        raise RuntimeError(f"{name}: no face-season had >= {RUN_LEN} window acquisitions")
    agg = res.groupby(["face_id", "year"]).stat.min().reset_index()

    src = agg[agg.face_id == "SOURCE-BOX"].sort_values("year")
    ev_year = ev.year
    src_ev = src[src.year == ev_year]
    fleet = agg[(agg.face_id != "SOURCE-BOX")]
    n_fleet, n_alarm = len(fleet), int((fleet.stat <= ALARM_Z).sum())
    print(f"\n== {name} ({event}) — {expectation} ==")
    print("source box, worst 3-run z_adj per year: "
          + "  ".join(f"{int(r.year)}:{r.stat:+.1f}" for r in src.itertuples()))
    if src_ev.empty:
        print(f"source box NOT TESTABLE in {ev_year} (too few window acquisitions)")
        verdict = "not testable"
    else:
        s = float(src_ev.stat.iloc[0])
        verdict = "CAUGHT" if s <= ALARM_Z else "missed"
        print(f"event year {ev_year}: stat {s:+.2f} -> {verdict} (threshold {ALARM_Z})")
    print(f"fleet context: {n_alarm}/{n_fleet} face-seasons alarm in the same windows "
          f"({100 * n_alarm / max(n_fleet, 1):.1f}%)")
    return {"event": name, "verdict": verdict,
            "stat": None if src_ev.empty else round(float(src_ev.stat.iloc[0]), 2),
            "fleet": f"{n_alarm}/{n_fleet}"}


def main() -> None:
    init_ee()
    summary = []
    for name, (lon, lat, event, pre_start, elev_min, slope_min, area_min,
               box_half, use_scar, expectation) in EVENTS.items():
        try:
            if use_scar:
                slon, slat, found = locate_scar(name, lon, lat, event, pre_start)
            else:
                slon, slat = lon, lat
            src_box = [slon - BOX_HALF * 1.2, slat - BOX_HALF, slon + BOX_HALF * 1.2, slat + BOX_HALF]
            faces = fleet_faces(lon, lat, elev_min, src_box, slope_min, area_min, box_half)
            path = extract_series(name, faces, src_box)
            summary.append(replay(name, path, event, expectation))
        except RuntimeError as e:
            print(f"\n== {name} FAILED: {e}")
            summary.append({"event": name, "verdict": f"failed: {e}", "stat": None, "fleet": ""})
    print("\n==== PHASE-0 SUMMARY ====")
    for s in summary:
        print(f"{s['event']:<10} stat {s['stat']}  {s['verdict']}  fleet alarms {s['fleet']}")


if __name__ == "__main__":
    main()
