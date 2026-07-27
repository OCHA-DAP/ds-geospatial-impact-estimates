"""RQ6 step 1 — GEE export: Sentinel-1 amplitude-change z-scores over the CEMS extents.

GEE hosts S1 GRD (amplitude) only — no SLC/coherence — so the DIY statistic is multi-temporal
BACKSCATTER change (standard in the GEE earthquake-damage literature), which is also usefully
independent of IMPACT/OSU's coherence approach:

  per pixel, per relative orbit:  z = (dB_post − mean(dB_pre)) / std(dB_pre)
  pre stack  = 12 months to the day before the event (2025-06-24 … 2026-06-23)
  post       = mean of acquisitions in the first ~2 weeks after (2026-06-25 … 2026-07-08)
  std floored at 0.5 dB (avoids divide-by-tiny on very stable pixels)
  bands VV & VH; per-orbit z kept separate, then combined as the max |z| across bands+orbits
  (damage can raise or lower amplitude; |z| captures both).

The pre-stack std IS the stability baseline from DESIGN.md: chronically variable pixels
(vegetation, water) get large std, so the same dB change scores a low z there. Output: one
GeoTIFF per CEMS area (10 m): bands [zmax, n_orbits]. Event: M7.5+M7.2 doublet 2026-06-24
22:05 UTC (USGS us6000t7zp/us6000t7zc).

Run: uv run --group etl --with earthengine-api python \
       exploratory/paper/artefacts/RQ6-diy-sar/scripts/rq6_gee_export.py
"""
from __future__ import annotations
import os, sys
import ee

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT, exist_ok=True)

PRE = ("2025-06-24", "2026-06-24")
POST = ("2026-06-25", "2026-07-08")
STD_FLOOR = 0.5  # dB
SCALE = 10


def cems_areas():
    """Latest CEMS analysed extent per aoi_name, exploded into disjoint parts
    (downloads are bbox-based; a dissolved multi-part area can span a huge bbox)."""
    from shapely.geometry import box
    ext = gp.cems_extent()
    latest = ext[ext.is_latest == True]  # noqa: E712
    out = []
    for name, sub in latest.groupby("aoi_name"):
        u = sub.geometry.make_valid().union_all().simplify(0.001)
        parts = list(getattr(u, "geoms", [u]))
        for i, part in enumerate(parts):
            if part.area * 1.2e10 < 0.05e6:  # skip slivers < 0.05 km2
                continue
            # downloads are bbox-based; tile any part whose bbox exceeds ~800 km2
            minx, miny, maxx, maxy = part.bounds
            bbox_km2 = (maxx - minx) * (maxy - miny) * 110 * 109
            slug = f"{name.replace(' ', '_').lower()}_{i}"
            # clip mask = the true extent geometry; download region = its plain bbox rectangle
            # (complex/holed region geometries trigger opaque 400s on the download endpoint)
            if bbox_km2 <= 120:
                out.append((slug, ee.Geometry(part.__geo_interface__),
                            ee.Geometry.Rectangle([minx, miny, maxx, maxy])))
                continue
            step = 0.08  # ~9 km tiles
            k = 0
            x = minx
            while x < maxx:
                y = miny
                while y < maxy:
                    t = part.intersection(box(x, y, x + step, y + step))
                    if not t.is_empty and t.area * 1.2e10 > 0.05e6:
                        b = t.bounds
                        out.append((f"{slug}_t{k}", ee.Geometry(t.__geo_interface__),
                                    ee.Geometry.Rectangle(list(b))))
                        k += 1
                    y += step
                x += step
    return out


def orbit_z(col, orbit, geom):
    """Per-pixel z of post vs pre stack for one relative orbit. Returns |z| max over VV/VH.
    Pre stack capped at the 30 most recent scenes and mean+std computed in ONE combined
    reducer pass — a full-year stack with separate reducers blows GEE's interactive memory
    limit ('User memory limit exceeded', HTTP 400 on download)."""
    oc = col.filter(ee.Filter.eq("relativeOrbitNumber_start", orbit))
    pre = oc.filterDate(*PRE).limit(30, "system:time_start", False)
    post = oc.filterDate(*POST)
    stats = pre.reduce(ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True))
    mean = stats.select([".*_mean"])
    std = stats.select([".*_stdDev"]).max(STD_FLOOR)
    z = post.mean().rename(["VV_mean", "VH_mean"]).subtract(mean).divide(std)
    return z.abs().reduce(ee.Reducer.max())  # max |z| over bands


def main():
    ee.Initialize()
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
          .select(["VV", "VH"]))

    for name, geom, rect in cems_areas():
        col = s1.filterBounds(geom)
        # orbits with BOTH >=8 pre acquisitions (a real baseline) and >=1 post
        orbits = col.filterDate(*POST).aggregate_array("relativeOrbitNumber_start").distinct().getInfo()
        usable = []
        for o in orbits:
            n_pre = col.filter(ee.Filter.eq("relativeOrbitNumber_start", o)).filterDate(*PRE).size().getInfo()
            n_post = col.filter(ee.Filter.eq("relativeOrbitNumber_start", o)).filterDate(*POST).size().getInfo()
            if n_pre >= 8 and n_post >= 1:
                usable.append((o, n_pre, n_post))
        if not usable:
            print(f"{name}: NO usable orbit, skipped")
            continue
        dst = os.path.join(OUT, f"z_{name}.tif")
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            print(f"{name}: exists, skipped", flush=True)
            continue
        zs = [orbit_z(col, o, geom) for o, _, _ in usable]
        zmax = ee.ImageCollection([z.rename("z") for z in zs]).max().rename("zmax")
        img = zmax.toFloat().clip(geom)
        import time
        import urllib.request
        for attempt in range(3):
            try:
                url = img.getDownloadURL({"scale": SCALE, "region": rect, "format": "GEO_TIFF",
                                          "crs": "EPSG:32619"})
                urllib.request.urlretrieve(url, dst)
                print(f"{name}: orbits {[(o, npre, npost) for o, npre, npost in usable]} -> {dst} "
                      f"({os.path.getsize(dst)/1e6:.1f} MB)", flush=True)
                break
            except Exception as e:  # degenerate tile geometry / transient 400 — log and move on
                if attempt == 2:
                    print(f"{name}: FAILED after 3 tries ({str(e)[:120]})", flush=True)
                else:
                    time.sleep(3)


if __name__ == "__main__":
    main()
