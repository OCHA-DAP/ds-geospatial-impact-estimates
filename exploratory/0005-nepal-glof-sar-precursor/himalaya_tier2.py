"""0005 step 11b — tier-2: the validated detector on tier-1's worst facets.

Reads himalaya_tier1.csv (season-mean VV per facet-year), scores each facet's
2026 season against its own other years (leave-one-out z), adjusts by the
median z of facets in the same 1-degree cell (falling back to the domain median
when a cell is thin), ranks, and pulls the FULL descending series for the worst
TOP_N facets to compute the validated worst-3-consecutive statistic — the same
number the historical analysis used, placed against the facet's own history.

Output: data/himalaya_tier2.csv (facet_id, tier1_z, t2_2026, t2 history json).

Run: uv run --group etl --with earthengine-api,geopandas python \
       exploratory/0005-nepal-glof-sar-precursor/himalaya_tier2.py
"""
from __future__ import annotations

import csv
import json
import os
import time

import ee
import numpy as np
import pandas as pd

from extract import init_ee, s1

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

TOP_N = 40
RUN_LEN, DOY_WIN, MIN_POOL = 3, 12, 10
SEASON = (152, 237)


def tier1_z() -> pd.DataFrame:
    t1 = pd.read_csv(os.path.join(DATA, "himalaya_tier1.csv"))
    rows = []
    for fid, g in t1.groupby("facet_id"):
        g = g.set_index("year").vv_db
        if len(g) < 5:
            continue
        for y, v in g.items():
            o = g.drop(y)
            if o.std(ddof=1) > 0.05:
                rows.append({"facet_id": fid, "year": y,
                             "z1": (v - o.mean()) / max(o.std(ddof=1), 0.3)})
    z = pd.DataFrame(rows)
    import geopandas as gpd

    fac = gpd.read_file(os.path.join(DATA, "facets_himalaya_final.geojson"))
    cent = fac.set_index("facet_id").geometry.centroid
    z["cell"] = z.facet_id.map(lambda f: f"{cent[f].x:.0f}_{cent[f].y:.0f}")
    med_cell = z.groupby(["cell", "year"]).z1.transform("median")
    n_cell = z.groupby(["cell", "year"]).z1.transform("size")
    med_dom = z.groupby("year").z1.transform("median")
    z["z1_adj"] = z.z1 - med_cell.where(n_cell >= 15, med_dom)
    return z


def main() -> None:
    init_ee()
    import geopandas as gpd

    z = tier1_z()
    z26 = z[z.year == 2026].sort_values("z1_adj")
    worst = z26.head(TOP_N)
    print(f"tier-1 2026: {len(z26)} facets scored; worst {TOP_N}: "
          f"{worst.z1_adj.min():+.1f} .. {worst.z1_adj.max():+.1f}")

    fac = gpd.read_file(os.path.join(DATA, "facets_himalaya_final.geojson"))
    sel = fac[fac.facet_id.isin(worst.facet_id)]
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry(g.__geo_interface__), {"facet_id": fid})
        for g, fid in zip(sel.geometry, sel.facet_id)
    ])
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    ts = os.path.join(DATA, "himalaya_tier2_ts.csv")
    if not (os.path.exists(ts) and os.path.getsize(ts) > 0):
        with open(ts, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["t", "orbit", "facet_id", "vv_db", "n_pix"])
            for year in range(2020, 2027):
                col = (s1().filterBounds(fc.geometry().bounds())
                       .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
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
                            raise RuntimeError(f"tier2 {year}: {e}") from e
                        time.sleep(20 * (attempt + 1))
                for r in got:
                    p = r["properties"]
                    w.writerow([p["t"], p["orbit"], p["facet_id"], p["vv_db"], p["n_pix"]])
                print(f"tier2 {year}: +{len(got)}", flush=True)

    df = pd.read_csv(ts, parse_dates=["t"])
    full = df.groupby(["facet_id", "orbit"])["n_pix"].transform("max")
    df = df[(df.n_pix >= 0.8 * full) & df.vv_db.notna()].copy()
    df["year"], df["doy"] = df.t.dt.year, df.t.dt.dayofyear
    out = []
    for (fid, orbit), g in df.groupby(["facet_id", "orbit"]):
        v = g.sort_values("t").reset_index(drop=True)
        doy, yr, vv = v.doy.values, v.year.values, v.vv_db.values
        zz = np.full(len(v), np.nan)
        for i in range(len(v)):
            dd = np.minimum(np.abs(doy - doy[i]), 365 - np.abs(doy - doy[i]))
            pool = (dd <= DOY_WIN) & (yr != yr[i])
            if pool.sum() >= MIN_POOL:
                zz[i] = (vv[i] - vv[pool].mean()) / vv[pool].std(ddof=1)
        v["z"] = zz
        out.append(v)
    zdf = pd.concat(out, ignore_index=True).dropna(subset=["z"])
    # regional control: with only worst-40 extracted, use each facet's z minus
    # the same-date median across the 40 — imperfect (the set is anomaly-biased,
    # which makes the adjustment conservative) and noted in the dashboard copy
    med = zdf.groupby(["orbit", "date" if "date" in zdf else "t"]).z.transform("median")
    zdf["z_adj"] = zdf.z - med
    seas = zdf[(zdf.doy >= SEASON[0]) & (zdf.doy <= SEASON[1])]
    rows = []
    for (fid, year), g in seas.groupby(["facet_id", "year"]):
        v = g.sort_values("t").z_adj.values
        if len(v) >= RUN_LEN:
            rows.append({"facet_id": fid, "year": int(year),
                         "stat": round(float(min(max(v[i:i + RUN_LEN])
                                                 for i in range(len(v) - RUN_LEN + 1))), 2)})
    res = pd.DataFrame(rows)
    dst = os.path.join(DATA, "himalaya_tier2.csv")
    with open(dst, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["facet_id", "tier1_z26", "t2_2026", "t2_hist"])
        for fid in worst.facet_id:
            sub = res[res.facet_id == fid].set_index("year").stat
            w.writerow([fid, round(float(worst[worst.facet_id == fid].z1_adj.iloc[0]), 2),
                        sub.get(2026, ""), json.dumps(sub.drop(2026, errors="ignore").to_dict())])
    print(f"-> {dst}")
    top = res[res.year == 2026].sort_values("stat").head(10)
    print("worst tier-2 2026 stats:", "  ".join(f"{r.facet_id}:{r.stat:+.1f}"
                                                for r in top.itertuples()))


if __name__ == "__main__":
    main()
