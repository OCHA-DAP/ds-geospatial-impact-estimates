"""0005 step 10b — score every facet and assemble the live status dashboard.

Per facet: leave-one-out climatology z per orbit, minus the same-date
all-facet median (the regional control), then two statistics:
  season_stat  worst 3-consecutive z_adj inside Jun 1 - Aug 25, per year —
               the detector statistic used throughout 0005;
  live_stat    worst 3-consecutive z_adj in the most recent 90 days of data —
               "where the face sits right now".

Tiering places live_stat in the HISTORICAL null = all facet-season stats from
2020-2025 (pre-collapse years, every facet): percentile < 1 -> critical,
< 5 -> elevated, < 15 -> watch, else quiet. No threshold is privileged; the
tier is a rank statement against the region's own history.

Output: dashboard HTML (from live_dashboard_template.html) with the facet
polygons, per-facet histories, and a GEE hillshade basemap embedded — written
to data/ and pages/langtang-facet-watch/.

Run: uv run --group etl --with rasterio,matplotlib,geopandas python \
       exploratory/0005-nepal-glof-sar-precursor/live_build.py
"""
from __future__ import annotations

import base64
import datetime as dt
import io
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
PAGES = os.path.join(HERE, "..", "..", "pages", "langtang-facet-watch")

REGION = [84.9, 27.9, 86.3, 28.7]
RUN_LEN, DOY_WIN, MIN_POOL, MIN_FACE_DATE = 3, 12, 10, 30
SEASON = (152, 237)
TIERS = [(1, "critical"), (5, "elevated"), (15, "watch"), (100, "quiet")]


def loo_z(df: pd.DataFrame) -> pd.DataFrame:
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
    return pd.concat(out, ignore_index=True).dropna(subset=["z"])


def worst_run(vals: np.ndarray) -> float | None:
    if len(vals) < RUN_LEN:
        return None
    return float(min(max(vals[i:i + RUN_LEN]) for i in range(len(vals) - RUN_LEN + 1)))


def main() -> None:
    import geopandas as gpd
    import rasterio

    df = pd.read_csv(os.path.join(DATA, "live_facet_ts.csv"), parse_dates=["t"])
    full = df.groupby(["facet_id", "orbit"])["n_pix"].transform("max")
    df = df[(df.n_pix >= 0.8 * full) & df.vv_db.notna()].copy()
    df["year"], df["doy"] = df.t.dt.year, df.t.dt.dayofyear
    df["date"] = df.t.dt.date
    df = df[df.groupby(["facet_id", "orbit"]).year.transform("nunique") >= 4]
    last_t = df.t.max()
    print(f"{df.facet_id.nunique()} facets scored, last acquisition {last_t:%Y-%m-%d}")

    z = loo_z(df)
    med = z.groupby(["orbit", "date"]).z.agg(["median", "size"])
    z = z.join(med, on=["orbit", "date"])
    z = z[z["size"] >= MIN_FACE_DATE].copy()
    z["z_adj"] = z.z - z["median"]

    seas = z[(z.doy >= SEASON[0]) & (z.doy <= SEASON[1])]
    season_stats = {}
    for (fid, year), g in seas.groupby(["facet_id", "year"]):
        s = worst_run(g.sort_values("t").z_adj.values)
        if s is not None:
            season_stats.setdefault(fid, {})[int(year)] = round(s, 2)
    null = np.array([s for d in season_stats.values()
                     for y, s in d.items() if y < 2026])
    print(f"historical null: {len(null)} facet-seasons "
          f"(p50 {np.percentile(null, 50):+.2f}, p1 {np.percentile(null, 1):+.2f})")

    live_cut = last_t - pd.Timedelta(days=90)
    live_stats = {}
    for fid, g in z[z.t >= live_cut].groupby("facet_id"):
        s = worst_run(g.sort_values("t").z_adj.values)
        if s is not None:
            live_stats[fid] = round(s, 2)

    facets = gpd.read_file(os.path.join(DATA, "facets_langtang_final.geojson"))
    # static hazard-chain factors (consequence triage, never detection): each
    # factor as a percentile rank across the layer, chain = their mean
    chain = {}
    hc_path = os.path.join(DATA, "hazard_chain_langtang.csv")
    if os.path.exists(hc_path):
        hc = pd.read_csv(hc_path).set_index("facet_id")
        ranks = hc.rank(pct=True) * 100
        for fid in hc.index:
            chain[fid] = {
                "drop": int(hc.drop_m[fid]), "lake": int(hc.lake_pct[fid]),
                "pop": int(hc.pop_50k[fid]),
                "chain": round(float(ranks.loc[fid].mean()), 1),
            }
    out = []
    tiers_count = {"critical": 0, "elevated": 0, "watch": 0, "quiet": 0, "nodata": 0}
    for _, r in facets.iterrows():
        fid = r.facet_id
        live = live_stats.get(fid)
        if live is None:
            tier, pct = "nodata", None
        else:
            pct = round(100 * (null <= live).mean(), 1)
            tier = next(t for lim, t in TIERS if pct < lim or lim == 100)
        tiers_count[tier] += 1
        geom = max(getattr(r.geometry, "geoms", [r.geometry]), key=lambda g: g.area)
        poly = [[round(x, 4), round(y, 4)] for x, y in
                geom.simplify(0.0008).exterior.coords]
        rec = {"id": fid, "aspect": r.aspect, "km2": round(r.km2, 2),
               "tier": tier, "live": live, "pct": pct,
               "years": season_stats.get(fid, {}), "poly": poly}
        if fid in chain:
            rec.update(chain[fid])
            if pct is not None:
                # attention = anomaly extremity x consequence rank (both 0-100)
                rec["attn"] = round((100 - pct) * rec["chain"] / 100, 1)
        out.append(rec)
    print("tiers:", tiers_count)

    with rasterio.open(os.path.join(DATA, "live_hillshade.tif")) as src:
        h = src.read(1)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    plt.imsave(buf, h, cmap="gray", vmin=60, vmax=255, format="png")
    hill_b64 = base64.b64encode(buf.getvalue()).decode()

    payload = {
        "generated": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "last_acq": f"{last_t:%Y-%m-%d}",
        "region": REGION,
        "tiers": tiers_count,
        "null_n": int(len(null)),
        "facets": out,
    }
    with open(os.path.join(HERE, "reports", "live_dashboard_template.html")) as f:
        html = f.read()
    html = html.replace("{{DATA}}", json.dumps(payload, separators=(",", ":")))
    html = html.replace("{{HILLSHADE}}", hill_b64)
    dst = os.path.join(DATA, "langtang-facet-watch.html")
    with open(dst, "w") as f:
        f.write(html)
    print(f"{len(html) / 1e6:.1f} MB -> {dst}")

    os.makedirs(PAGES, exist_ok=True)
    page = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>Langtang Facet Watch</title>\n</head>\n<body>\n"
            "<style>.home-link{display:inline-block;margin:10px 12px;padding:6px 12px;"
            "font:500 13px/1 'IBM Plex Mono',monospace;color:#2a78d6;background:#eaf2fb;"
            "border:1px solid #c9ddf3;border-radius:4px;text-decoration:none}"
            ".home-link:hover{background:#dcebf9}</style>\n"
            '<a class="home-link" href="../">← All analysis &amp; tools</a>\n'
            + html.replace("<title>Langtang Facet Watch</title>", "", 1)
            + "\n</body>\n</html>\n")
    with open(os.path.join(PAGES, "index.html"), "w") as f:
        f.write(page)
    print(f"pages copy -> {os.path.join(PAGES, 'index.html')}")


if __name__ == "__main__":
    main()
