"""0005 step 1 — GEE extraction for the 2026-08-26 Langtang Lirung glacier collapse.

Event: ice/rock detachment on the N flank of Langtang Lirung, 2026-08-26 02:52:10 UTC
(USGS us7000tbwb, M5.2-equivalent seismic signal; second collapse us7000tc90 ~3 h later).
Published source coordinates: 28.28532N 85.52515E (Petley early analysis) and
28.2765N 85.5194E (Petley, eos.org landslide blog). Debris flow ran ~100 km down the
Lende Khola -> Trishuli (Rasuwagadhi).

Question: do Sentinel-1 backscatter time series show precursor change on that face in
the weeks before the collapse? Three extractions, all S1_GRD IW VV+VH, per relative
orbit (19 desc / 85 asc / 121 desc — geometry differs, so orbits never mix):

  1. AOI time series 2020-01-01 -> now: mean VV/VH dB + pixel count per acquisition
     over the source box and two elevation-matched control boxes on the same massif.
     Prior monsoons give the seasonal envelope; a real precursor moves the source
     box away from its envelope while the controls stay inside theirs.
  2. Scar map: orbit 85's first post-event scene (2026-08-28) vs the same orbit's
     Jun-Aug 2026 pre-event stack -> per-pixel z. Locates the actual detachment,
     rather than trusting news coordinates.
  3. Pre-event z maps: every Jun 1 - Aug 25 2026 acquisition scored against the same
     orbit's 2023-2025 monsoon-season stack (mean/std, std floored) over the source
     box. analysis.py turns these into an anomalous-pixel-fraction series.

Run: uv run --group etl --with earthengine-api python \
       exploratory/0005-nepal-glof-sar-precursor/extract.py
"""
from __future__ import annotations

import datetime as dt
import os
import time
import urllib.request

import ee
import google.auth

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

EVENT_UTC = "2026-08-26T02:52:10"
STD_FLOOR = 0.5  # dB, same floor as RQ6 — avoids divide-by-tiny on stable pixels
SCALE = 10

# lon/lat boxes. Source covers both published coordinates + ~700 m margin.
AOIS = {
    "source": [85.512, 28.269, 85.533, 28.293],
    "control_w": [85.470, 28.270, 85.491, 28.293],
    "control_e": [85.560, 28.270, 85.581, 28.293],
}
# wider box for the scar map: source face + upper Lende Khola runout to the N
SCAR_BOX = [85.480, 28.250, 85.580, 28.340]

TS_START = "2020-01-01"
PREMAP_RANGE = ("2026-06-01", "2026-08-26")  # acquisitions to score (pre-event)
BASELINE_YEARS = (2023, 2024, 2025)  # monsoon-season baseline for the z maps
BASELINE_MONSOON = ("-06-01", "-09-15")  # month-day window within each baseline year


def init_ee() -> None:
    """The persistent ~/.config/earthengine token is revoked; use gcloud ADC.
    Fails loudly with the fix if ADC is missing too."""
    try:
        creds, _ = google.auth.default(
            scopes=[
                "https://www.googleapis.com/auth/earthengine",
                "https://www.googleapis.com/auth/cloud-platform",
            ]
        )
        ee.Initialize(credentials=creds, project="ee-zackarno")
    except Exception as e:  # noqa: BLE001 — re-raise with the actionable fix
        raise RuntimeError(
            "Earth Engine init failed. The stored earthengine token is revoked; "
            "this script needs gcloud ADC: run `gcloud auth application-default login` "
            f"(project ee-zackarno). Underlying error: {e}"
        ) from e


def s1() -> ee.ImageCollection:
    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .select(["VV", "VH"])
    )


def report_terrain() -> None:
    """Print mean elevation/slope per AOI from GLO30 so control comparability is
    on the record (controls should sit within a few hundred m of the source)."""
    coll = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM")
    # mosaic() drops the native projection (slope would compute on a 1-degree
    # pseudo-grid and come out near zero) — restore it explicitly
    dem = coll.mosaic().setDefaultProjection(coll.first().projection())
    slope = ee.Terrain.slope(dem)
    for name, box in AOIS.items():
        geom = ee.Geometry.Rectangle(box)
        stats = (
            dem.addBands(slope)
            .reduceRegion(ee.Reducer.mean(), geom, 30)
            .getInfo()
        )
        print(f"terrain {name}: elev {stats['DEM']:.0f} m, slope {stats['slope']:.1f} deg")


def extract_timeseries() -> None:
    """One CSV row per acquisition x AOI: mean VV/VH dB + valid-pixel count.
    Chunked by year — one whole-archive request trips GEE's interactive
    'Too many concurrent aggregations' limit."""
    dst = os.path.join(DATA, "s1_timeseries.csv")
    aoi_fc = ee.FeatureCollection(
        [ee.Feature(ee.Geometry.Rectangle(b), {"aoi": n}) for n, b in AOIS.items()]
    )
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)

    def per_image(img):
        return img.reduceRegions(aoi_fc, reducer, SCALE).map(
            lambda f: f.set(
                {
                    "t": img.date().format("YYYY-MM-dd'T'HH:mm"),
                    "orbit": img.get("relativeOrbitNumber_start"),
                    "pass": img.get("orbitProperties_pass"),
                    "platform": img.get("platform_number"),
                }
            )
        )

    rows = []
    first_year = int(TS_START[:4])
    for year in range(first_year, 2027):
        col = s1().filterBounds(ee.Geometry.Rectangle(AOIS["source"])).filterDate(
            f"{year}-01-01", f"{year + 1}-01-01"
        )
        fc = ee.FeatureCollection(col.map(per_image)).flatten()
        got = fc.getInfo()["features"]
        print(f"timeseries {year}: {len(got)} rows", flush=True)
        rows.extend(got)
    if not rows:
        raise RuntimeError("time-series extraction returned zero rows — check filters")
    import csv

    with open(dst, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "orbit", "pass", "platform", "aoi", "vv_db", "vh_db", "n_pix"])
        for r in rows:
            p = r["properties"]
            w.writerow(
                [
                    p["t"], p["orbit"], p["pass"], p["platform"], p["aoi"],
                    p.get("VV_mean"), p.get("VH_mean"), p.get("VV_count"),
                ]
            )
    print(f"timeseries: {len(rows)} rows -> {dst}")


def download(img: ee.Image, region: list[float], dst: str) -> None:
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        print(f"exists, skipped: {os.path.basename(dst)}")
        return
    rect = ee.Geometry.Rectangle(region)
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            url = img.toFloat().getDownloadURL(
                {"scale": SCALE, "region": rect, "format": "GEO_TIFF", "crs": "EPSG:32645"}
            )
            urllib.request.urlretrieve(url, dst)
            print(f"{os.path.basename(dst)}: {os.path.getsize(dst) / 1e6:.1f} MB")
            return
        except Exception as e:  # noqa: BLE001 — retried, then re-raised below
            last_err = e
            time.sleep(3)
    raise RuntimeError(f"download failed after 3 tries for {dst}: {last_err}") from last_err


def zscore(post: ee.Image, pre: ee.ImageCollection) -> ee.Image:
    """|z| of one scene vs a baseline stack, max over VV/VH (matches RQ6)."""
    stats = pre.reduce(ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True))
    mean = stats.select([".*_mean"])
    std = stats.select([".*_stdDev"]).max(STD_FLOOR)
    z = post.rename(["VV_mean", "VH_mean"]).subtract(mean).divide(std)
    return z.abs().reduce(ee.Reducer.max()).rename("zmax")


def extract_scar_map() -> None:
    """Post-event (orbit 85, 2026-08-28) vs that orbit's Jun-Aug 2026 pre-stack."""
    col = s1().filterBounds(ee.Geometry.Rectangle(SCAR_BOX)).filter(
        ee.Filter.eq("relativeOrbitNumber_start", 85)
    )
    post = col.filterDate("2026-08-26", "2026-08-30")
    n_post = post.size().getInfo()
    if n_post == 0:
        raise RuntimeError("no post-event orbit-85 scene found — expected 2026-08-28")
    pre = col.filterDate("2026-06-01", "2026-08-25")
    print(f"scar map: {n_post} post scene(s), {pre.size().getInfo()} pre scenes")
    download(zscore(post.mean(), pre), SCAR_BOX, os.path.join(DATA, "scar_z_orbit85.tif"))


def extract_preevent_maps() -> None:
    """Each pre-event 2026 acquisition vs same-orbit 2023-25 monsoon baseline."""
    src = ee.Geometry.Rectangle(AOIS["source"])
    col = s1().filterBounds(src)
    orbits = (
        col.filterDate(*PREMAP_RANGE)
        .aggregate_array("relativeOrbitNumber_start")
        .distinct()
        .getInfo()
    )
    for orbit in sorted(orbits):
        oc = col.filter(ee.Filter.eq("relativeOrbitNumber_start", orbit))
        base = oc.filter(
            ee.Filter.Or(
                *[ee.Filter.date(f"{y}{BASELINE_MONSOON[0]}", f"{y}{BASELINE_MONSOON[1]}")
                  for y in BASELINE_YEARS]
            )
        )
        n_base = base.size().getInfo()
        if n_base < 8:
            raise RuntimeError(f"orbit {orbit}: only {n_base} baseline scenes (<8)")
        scenes = oc.filterDate(*PREMAP_RANGE)
        ids = scenes.aggregate_array("system:index").getInfo()
        times = scenes.aggregate_array("system:time_start").getInfo()
        print(f"orbit {orbit}: {len(ids)} pre-event scenes, {n_base} baseline scenes")
        for sid, t in zip(ids, times):
            stamp = dt.datetime.fromtimestamp(t / 1000, dt.UTC).strftime("%Y%m%dT%H%M")
            img = ee.Image(f"COPERNICUS/S1_GRD/{sid}").select(["VV", "VH"])
            download(
                zscore(img, base),
                AOIS["source"],
                os.path.join(DATA, f"pre_z_orbit{orbit}_{stamp}.tif"),
            )


if __name__ == "__main__":
    init_ee()
    report_terrain()
    extract_timeseries()
    extract_scar_map()
    extract_preevent_maps()
