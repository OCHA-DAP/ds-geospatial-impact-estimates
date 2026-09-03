"""0005 step 11c — assemble the Himalaya-scale facet watch dashboard.

Tier-1 season z per facet-year (from himalaya_tier1.csv, cell-median adjusted as
in himalaya_tier2.tier1_z), the 2026 value placed as a percentile in the domain
null of prior-year values; tier-2 validated stats attached where computed.
Reuses live_dashboard_template.html with domain-specific copy swapped in.

Run: uv run --group etl --with rasterio,matplotlib,geopandas python \
       exploratory/0005-nepal-glof-sar-precursor/himalaya_build.py
"""
from __future__ import annotations

import base64
import datetime as dt
import io
import json
import os

import numpy as np
import pandas as pd

from himalaya_batch import DOMAIN  # the batch pipeline's full-arc domain
from himalaya_tier2 import tier1_z

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
PAGES = os.path.join(HERE, "..", "..", "pages", "himalaya-facet-watch")
TIERS = [(1, "critical"), (5, "elevated"), (15, "watch"), (100, "quiet")]


def main() -> None:
    import geopandas as gpd
    import rasterio

    z = tier1_z()
    hist = z[z.year < 2026]
    null = hist.z1_adj.values
    print(f"domain null: {len(null)} facet-seasons "
          f"(p50 {np.percentile(null, 50):+.2f}, p1 {np.percentile(null, 1):+.2f})")
    cur = z[z.year == 2026].set_index("facet_id").z1_adj

    t2 = {}
    t2p = os.path.join(DATA, "himalaya_tier2.csv")
    if os.path.exists(t2p):
        for _, r in pd.read_csv(t2p).iterrows():
            t2[r.facet_id] = r.t2_2026 if pd.notna(r.t2_2026) else None

    basins, facet_basin = {}, {}
    bp = os.path.join(DATA, "basins_himalaya.json")
    if os.path.exists(bp):
        bj = json.load(open(bp))
        basins, facet_basin = bj["basins"], bj["facet_basin"]

    facets = gpd.read_file(os.path.join(DATA, "facets_himalaya_final.geojson"))
    # background band for the context chart: per-year quantiles of the statistic
    bg = {str(int(y)): [round(float(np.percentile(g.z1_adj, q)), 2) for q in (10, 50, 90)]
          for y, g in z.groupby("year")}
    from shapely.geometry import Point

    scar = Point(85.52284, 28.28648)  # Langtang detachment centroid
    collapse_ids = set(facets[facets.geometry.contains(scar)].facet_id)
    if not collapse_ids:
        # the containing fragment fell below the arc layer's 0.5 km2 cut —
        # take the nearest facet within 2 km instead
        d = facets.to_crs(32645).distance(
            gpd.GeoSeries([scar], crs=4326).to_crs(32645).iloc[0])
        if d.min() <= 2000:
            collapse_ids = {facets.iloc[int(d.idxmin())].facet_id}
    chain = {}
    hc_path = os.path.join(DATA, "hazard_chain_himalaya.csv")
    if os.path.exists(hc_path):
        hc = pd.read_csv(hc_path).set_index("facet_id")
        ranks = hc.rank(pct=True) * 100
        for fid in hc.index:
            chain[fid] = {"drop": int(hc.drop_m[fid]), "lake": int(hc.lake_pct[fid]),
                          "pop": int(hc.pop_50k[fid]),
                          "chain": round(float(ranks.loc[fid].mean()), 1)}
    years_by_facet = {fid: {int(y): round(v, 2) for y, v in g.set_index("year").z1_adj.items()}
                      for fid, g in z.groupby("facet_id")}
    out, tiers_count = [], {"critical": 0, "elevated": 0, "watch": 0, "quiet": 0, "nodata": 0}
    for _, r in facets.iterrows():
        fid = r.facet_id
        live = round(float(cur[fid]), 2) if fid in cur.index else None
        if live is None:
            tier, pct = "nodata", None
        else:
            pct = round(100 * (null <= live).mean(), 1)
            tier = next(t for lim, t in TIERS if pct < lim or lim == 100)
        tiers_count[tier] += 1
        geom = max(getattr(r.geometry, "geoms", [r.geometry]), key=lambda g: g.area)
        poly = [[round(x, 4), round(y, 4)] for x, y in geom.simplify(0.001).exterior.coords]
        rec = {"id": fid, "aspect": r.aspect, "km2": round(r.km2, 2), "tier": tier,
               "live": live, "pct": pct,
               "years": {y: v for y, v in years_by_facet.get(fid, {}).items() if y < 2026},
               "poly": poly}
        if fid in t2:
            rec["t2"] = t2[fid]
        if fid in chain:
            rec.update(chain[fid])
            if pct is not None:
                rec["attn"] = round((100 - pct) * rec["chain"] / 100, 1)
        if fid in facet_basin:
            rec["basin"] = facet_basin[fid]
        if fid in collapse_ids:
            rec["collapse"] = True
        out.append(rec)
    print("collapse facet(s):", collapse_ids or "none found")
    print("tiers:", tiers_count)

    with rasterio.open(os.path.join(DATA, "himalaya_hillshade.tif")) as src:
        h = src.read(1)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    plt.imsave(buf, h, cmap="gray", vmin=60, vmax=255, format="png")

    payload = {
        "generated": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "last_acq": "2026 monsoon season to date",
        "region": DOMAIN,
        "tiers": tiers_count,
        "null_n": int(len(null)),
        "facets": out,
        "basins": basins,
        "bg": bg,
    }
    with open(os.path.join(HERE, "reports", "live_dashboard_template.html")) as f:
        html = f.read()
    import re as _re

    html = (html
            .replace("Langtang Facet Watch",
                     "Central Himalaya - Experimental Facet Watch Analyses")
            .replace("Langtang pilot region", "central Himalaya 82–89°E")
            .replace("last image ${DATA.last_acq}", "coverage ${DATA.last_acq}")
            .replace("Tier · percentile of the last 90 days vs 2020–25 history",
                     "Tier · percentile of the 2026 season vs 2020–25 history")
            .replace("Last-90d stat", "2026 season stat"))
    html = _re.sub(r"worst\s+recent 3-pass morning-radar\s+anomaly",
                   "2026 season-mean morning-radar anomaly (the scalable "
                   "screening statistic)", html)
    html = html.replace("{{DATA}}", json.dumps(payload, separators=(",", ":")))
    html = html.replace("{{HILLSHADE}}", base64.b64encode(buf.getvalue()).decode())
    dst = os.path.join(DATA, "himalaya-facet-watch.html")
    with open(dst, "w") as f:
        f.write(html)
    print(f"{len(html) / 1e6:.1f} MB -> {dst}")

    os.makedirs(PAGES, exist_ok=True)
    page = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>Central Himalaya - Experimental Facet Watch Analyses</title>\n</head>\n<body>\n"
            "<style>.home-link{display:inline-block;margin:10px 12px;padding:6px 12px;"
            "font:500 13px/1 'IBM Plex Mono',monospace;color:#2a78d6;background:#eaf2fb;"
            "border:1px solid #c9ddf3;border-radius:4px;text-decoration:none}"
            ".home-link:hover{background:#dcebf9}</style>\n"
            '<a class="home-link" href="../">← All analysis &amp; tools</a>\n'
            + html.replace("<title>Central Himalaya - Experimental Facet Watch Analyses</title>", "", 1)
            + "\n</body>\n</html>\n")
    with open(os.path.join(PAGES, "index.html"), "w") as f:
        f.write(page)
    print(f"pages copy -> {os.path.join(PAGES, 'index.html')}")


if __name__ == "__main__":
    main()
