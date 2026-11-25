"""0005 step 8 — retest the two history-test misses for measurement artefacts.

Hypothesis (review of finding 5): the misses reflect the experiment's setup,
not the detector — Sedongpu's single 2.4 km box may sit on the wrong part of a
~4 km-long detachment (AOI placement), and Marmolada was averaged over a box
~1000x the serac's footprint (aggregation scale).

Retests, both reusing the already-extracted regional fleets for the same-date
median adjustment:

  sedongpu  Tile the whole post-event change zone (every |z|>=3 cluster within
            6 km of the published point in hist_scar_sedongpu.tif) into ~1.3 km
            tiles and replay the detector on each. Operationally honest: a facet
            system watches many small units, so the event is caught if ANY tile
            over the detachment alarms pre-event. Multiple-testing context is
            reported (same statistic for every tile in every non-event year).
  marmolada A ~400 m micro-box centred on the published serac (46.437N
            11.852E). GRD's real resolution is ~20 m, so a 40x40-px box mean is
            statistically thin — reported with that caveat either way.

Run: uv run --group etl --with earthengine-api,rasterio,scipy python \
       exploratory/0005-nepal-glof-sar-precursor/miss_retest.py
"""
from __future__ import annotations

import csv
import os
import time

import ee
import numpy as np

from extract import init_ee, s1

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

RUN_LEN, ALARM_Z, DOY_WIN, MIN_POOL = 3, -2.0, 12, 10
WINDOW_DAYS = 90
TILE_DEG = 0.012  # ~1.3 km


def sedongpu_tiles() -> list[tuple[str, list[float]]]:
    """Tiles covering every large change cluster near the published point."""
    import rasterio
    import rasterio.warp
    from scipy import ndimage

    plon, plat = 94.92, 29.81
    with rasterio.open(os.path.join(DATA, "hist_scar_sedongpu.tif")) as src:
        z = src.read(1)
        lab, n = ndimage.label(np.abs(z) >= 3)
        sizes = np.bincount(lab.ravel())[1:]
        keep = np.zeros_like(lab, dtype=bool)
        for ci in np.nonzero(sizes >= 50)[0]:
            rr, cc = np.nonzero(lab == ci + 1)
            xs, ys = rasterio.transform.xy(src.transform, rr, cc)
            glon, glat = rasterio.warp.transform(src.crs, "EPSG:4326",
                                                 [float(np.mean(xs))], [float(np.mean(ys))])
            if np.hypot((glon[0] - plon) * 96.2, (glat[0] - plat) * 111) <= 6:
                keep |= lab == ci + 1
        rr, cc = np.nonzero(keep)
        xs, ys = rasterio.transform.xy(src.transform, rr, cc)
        lons, lats = rasterio.warp.transform(src.crs, "EPSG:4326", xs, ys)
    lons, lats = np.array(lons), np.array(lats)
    tiles = []
    x0 = lons.min()
    while x0 < lons.max():
        y0 = lats.min()
        while y0 < lats.max():
            inside = ((lons >= x0) & (lons < x0 + TILE_DEG)
                      & (lats >= y0) & (lats < y0 + TILE_DEG))
            if inside.sum() * 4e-4 >= 0.15:  # >=0.15 km2 of change (20 m px)
                tiles.append((f"T{len(tiles):02d}", [x0, y0, x0 + TILE_DEG, y0 + TILE_DEG]))
            y0 += TILE_DEG
        x0 += TILE_DEG
    print(f"sedongpu: {len(tiles)} tiles over the change zone")
    return tiles


def extract_boxes(name: str, boxes: list[tuple[str, list[float]]]) -> str:
    dst = os.path.join(DATA, f"retest_ts_{name}.csv")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        print(f"{name}: retest series exists, skipped")
        return dst
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Rectangle(b), {"face_id": bid}) for bid, b in boxes
    ])
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    bounds = fc.geometry().bounds()

    def per_image(img):
        return img.reduceRegions(fc, reducer, 10).map(
            lambda f: ee.Feature(None, {
                "t": img.date().format("YYYY-MM-dd'T'HH:mm"),
                "orbit": img.get("relativeOrbitNumber_start"),
                "face_id": f.get("face_id"),
                "vv_db": f.get("VV_mean"),
                "n_pix": f.get("VV_count"),
            })
        )

    with open(dst, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t", "orbit", "face_id", "vv_db", "n_pix"])
        for year in range(2015, 2025):
            col = (s1().filterBounds(bounds).filterDate(f"{year}-01-01", f"{year + 1}-01-01")
                   .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING")))
            fcoll = ee.FeatureCollection(col.map(per_image)).flatten().filter(
                ee.Filter.notNull(["vv_db"]))
            for attempt in range(4):
                try:
                    got = fcoll.getInfo()["features"]
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == 3:
                        raise RuntimeError(f"{name} {year}: {e}") from e
                    time.sleep(15 * (attempt + 1))
            for r in got:
                p = r["properties"]
                w.writerow([p["t"], p["orbit"], p["face_id"], p["vv_db"], p["n_pix"]])
            print(f"{name} {year}: +{len(got)}", flush=True)
    return dst


def loo_z_frame(df):
    import pandas as pd

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
    return pd.concat(out, ignore_index=True).dropna(subset=["z"])


def retest(name: str, retest_csv: str, fleet_csv: str, event: str,
           min_face_date: int) -> None:
    import pandas as pd

    ev = pd.Timestamp(event)

    def prep(path):
        df = pd.read_csv(path, parse_dates=["t"])
        full = df.groupby(["face_id", "orbit"])["n_pix"].transform("max")
        df = df[(df.n_pix >= 0.8 * full) & df.vv_db.notna()].copy()
        df["year"], df["doy"] = df.t.dt.year, df.t.dt.dayofyear
        df["date"] = df.t.dt.date
        return df[df.groupby(["face_id", "orbit"]).year.transform("nunique") >= 3]

    boxes = prep(retest_csv)
    fleet = prep(fleet_csv)
    fleet = fleet[fleet.face_id != "SOURCE-BOX"]
    zb, zf = loo_z_frame(boxes), loo_z_frame(fleet)
    med = zf.groupby(["orbit", "date"]).z.agg(["median", "size"])
    zb = zb.join(med, on=["orbit", "date"])
    zb = zb[zb["size"] >= min_face_date].copy()
    zb["z_adj"] = zb.z - zb["median"]

    w1 = ev.dayofyear
    w0 = (ev - pd.Timedelta(days=WINDOW_DAYS)).dayofyear
    in_win = ((zb.doy > w0) & (zb.doy <= w1)) if w0 < w1 else ((zb.doy > w0) | (zb.doy <= w1))
    seas = zb[in_win].copy()
    if w0 > w1:
        seas.loc[seas.doy > w0, "year"] += 1
    rows = []
    for (fid, year, orbit), g in seas.groupby(["face_id", "year", "orbit"]):
        v = g.sort_values("t").z_adj.values
        if len(v) >= RUN_LEN:
            rows.append({"face_id": fid, "year": year,
                         "stat": min(max(v[i:i + RUN_LEN]) for i in range(len(v) - RUN_LEN + 1))})
    res = pd.DataFrame(rows).groupby(["face_id", "year"]).stat.min().reset_index()
    ev_year = ev.year
    print(f"\n== {name} retest ({event}) ==")
    evr = res[res.year == ev_year].sort_values("stat")
    if evr.empty:
        print("event year not testable")
        return
    print(f"event year, per box/tile (worst first): "
          + "  ".join(f"{r.face_id}:{r.stat:+.1f}" for r in evr.itertuples()))
    best = evr.iloc[0]
    caught = best.stat <= ALARM_Z
    print(f"best unit {best.face_id}: {best.stat:+.2f} -> "
          f"{'CAUGHT' if caught else 'still missed'} at {ALARM_Z}")
    # multiple-testing context: min-over-units statistic in every other year
    other = res[res.year != ev_year].groupby("year").stat.min()
    n_units = res.face_id.nunique()
    print(f"min-over-{n_units}-units stat, other years: "
          + "  ".join(f"{y}:{s:+.1f}" for y, s in other.items()))
    print(f"other-year min-stats <= {ALARM_Z}: {(other <= ALARM_Z).sum()}/{len(other)} "
          f"(the false-alarm cost of watching {n_units} units)")


if __name__ == "__main__":
    init_ee()
    tiles = sedongpu_tiles()
    p = extract_boxes("sedongpu", tiles)
    retest("sedongpu", p, os.path.join(DATA, "hist_ts_sedongpu.csv"), "2018-10-16", 6)
    half = 0.002  # ~400 m micro-box on the published serac coordinate
    mb = [("MICRO", [11.852 - half / 0.7, 46.437 - half, 11.852 + half / 0.7, 46.437 + half])]
    p = extract_boxes("marmolada", mb)
    retest("marmolada", p, os.path.join(DATA, "hist_ts_marmolada.csv"), "2022-07-03", 3)
