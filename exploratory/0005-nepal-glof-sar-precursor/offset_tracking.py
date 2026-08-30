"""0005 step 5 — amplitude offset tracking: was the block sliding before it fell?

The wetness detector saw nothing block-specific at the final pre-event pass
(39 h out). This asks whether a MOTION method could have: cross-correlate
Sentinel-1 speckle patches between consecutive same-orbit GRD acquisitions and
look for coherent surface displacement inside the future scar.

Pairs (morning/descending orbits, 12-day baselines):
  orbit 19 : 2026-08-12 -> 2026-08-24  (ends 39 h before collapse)
  orbit 121: 2026-08-07 -> 2026-08-19  (ends 7 days before)
  reference pairs one cycle earlier (07-31->08-12, 07-26->08-07) give the
  noise floor of the method on this terrain in monsoon.

Method: phase cross-correlation (skimage) on overlapping 64x64-px (640 m)
windows of linear-power amplitude, 10x subpixel upsampling, stepping 16 px.
Each window yields (dy, dx) in pixels (10 m) and a normalised correlation peak.
Windows with peak < NCC_MIN are 'decorrelated' — motion there is unmeasurable,
which is reported as its own state, never conflated with 'no motion'.

Run: uv run --group etl --with earthengine-api,rasterio,matplotlib,scikit-image \
       python exploratory/0005-nepal-glof-sar-precursor/offset_tracking.py
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import rasterio.warp
from rasterio.windows import from_bounds
from skimage.registration import phase_cross_correlation

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FIGS = os.path.join(HERE, "figs")
os.makedirs(FIGS, exist_ok=True)

# chip covering the detachment face + surrounding terrain (off-glacier = control)
CHIP = [85.495, 28.255, 85.560, 28.315]
SOURCE_BOX = (85.512, 28.269, 85.533, 28.293)
PAIRS = [  # (orbit, date_a, date_b, role)
    (19, "2026-08-12", "2026-08-24", "final"),
    (121, "2026-08-07", "2026-08-19", "final"),
    (19, "2026-07-31", "2026-08-12", "reference"),
    (121, "2026-07-26", "2026-08-07", "reference"),
]
WIN, STEP, UPS = 64, 16, 10
NCC_MIN = 0.06  # empirical floor for a real correlation peak in these chips


def download_chips() -> None:
    import ee

    from extract import init_ee, s1

    init_ee()
    col = s1().filterBounds(ee.Geometry.Rectangle(CHIP))
    for orbit, da, db_, _ in PAIRS:
        for d in (da, db_):
            dst = os.path.join(DATA, f"amp_orbit{orbit}_{d}.tif")
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                continue
            oc = col.filter(ee.Filter.eq("relativeOrbitNumber_start", orbit)).filterDate(
                d, f"{d}T23:59"
            )
            n = oc.size().getInfo()
            if n != 1:
                raise RuntimeError(f"orbit {orbit} {d}: expected 1 scene, got {n}")
            img = oc.first().select("VV").toFloat()
            url = img.getDownloadURL(
                {"scale": 10, "region": ee.Geometry.Rectangle(CHIP),
                 "format": "GEO_TIFF", "crs": "EPSG:32645"}
            )
            import urllib.request

            urllib.request.urlretrieve(url, dst)
            print(f"downloaded {os.path.basename(dst)}")


def read_pair(orbit: int, da: str, db_: str):
    def rd(d):
        with rasterio.open(os.path.join(DATA, f"amp_orbit{orbit}_{d}.tif")) as src:
            a = src.read(1)
            l, b, r, t = rasterio.warp.transform_bounds("EPSG:4326", src.crs, *SOURCE_BOX)
            win = from_bounds(l, b, r, t, src.transform)
            box = (slice(int(win.row_off), int(win.row_off + win.height)),
                   slice(int(win.col_off), int(win.col_off + win.width)))
        return 10 ** (a / 10.0), box  # dB -> linear power for correlation

    a, box = rd(da)
    b, _ = rd(db_)
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    return a[:h, :w], b[:h, :w], box


def track(a: np.ndarray, b: np.ndarray):
    """Windowed phase cross-correlation. Returns per-window dy,dx (px), NCC peak."""
    rows = range(0, a.shape[0] - WIN, STEP)
    cols = range(0, a.shape[1] - WIN, STEP)
    dy = np.full((len(list(rows)), len(list(cols))), np.nan)
    dx, pk = dy.copy(), dy.copy()
    cy = np.array([r + WIN // 2 for r in range(0, a.shape[0] - WIN, STEP)])
    cx = np.array([c + WIN // 2 for c in range(0, a.shape[1] - WIN, STEP)])
    for i, r in enumerate(range(0, a.shape[0] - WIN, STEP)):
        for j, c in enumerate(range(0, a.shape[1] - WIN, STEP)):
            wa = a[r:r + WIN, c:c + WIN]
            wb = b[r:r + WIN, c:c + WIN]
            if not (np.isfinite(wa).all() and np.isfinite(wb).all()):
                continue
            wa = (wa - wa.mean()) / (wa.std() + 1e-12)
            wb = (wb - wb.mean()) / (wb.std() + 1e-12)
            shift, error, _ = phase_cross_correlation(wa, wb, upsample_factor=UPS,
                                                      normalization=None)
            # correlation peak height ~ 1 - error for phase_cross_correlation
            dy[i, j], dx[i, j], pk[i, j] = shift[0], shift[1], 1 - error
    return cy, cx, dy, dx, pk


def in_box(cy, cx, box) -> np.ndarray:
    r0, r1 = box[0].start, box[0].stop
    c0, c1 = box[1].start, box[1].stop
    return (cy[:, None] >= r0) & (cy[:, None] < r1) & (cx[None, :] >= c0) & (cx[None, :] < c1)


def main() -> None:
    download_chips()
    fig, axes = plt.subplots(2, 2, figsize=(10, 8.5))
    print(f"window {WIN * 10} m, step {STEP * 10} m, subpixel 1/{UPS} px "
          f"(1 px = 10 m); decorrelated = peak < {NCC_MIN}")
    for ax, (orbit, da, db_, role) in zip(axes.ravel(), PAIRS):
        a, b, box = read_pair(orbit, da, db_)
        cy, cx, dy, dx, pk = track(a, b)
        mag = np.hypot(dy, dx) * 10.0  # metres
        ok = pk >= NCC_MIN
        face = in_box(cy, cx, box)
        stats = {}
        for name, m in (("face", face), ("surround", ~face)):
            sel = ok & m & np.isfinite(mag)
            n_all = (m & np.isfinite(pk)).sum()
            stats[name] = (sel.sum(), n_all,
                           np.nanmedian(mag[sel]) if sel.any() else np.nan)
        # whole chips carry a common co-registration offset between GRD products
        # (several m is normal); real face motion is the DIFFERENTIAL against the
        # surrounding terrain, after removing the surround's median shift vector
        sel_s = ok & ~face & np.isfinite(dy)
        med_dy, med_dx = np.nanmedian(dy[sel_s]), np.nanmedian(dx[sel_s])
        sel_f = ok & face & np.isfinite(dy)
        diff = np.hypot(dy[sel_f] - med_dy, dx[sel_f] - med_dx) * 10.0
        print(f"orbit {orbit} {da}->{db_} ({role}): "
              f"face {stats['face'][0]}/{stats['face'][1]} windows correlated, "
              f"median |shift| {stats['face'][2]:.1f} m | "
              f"surround {stats['surround'][0]}/{stats['surround'][1]}, "
              f"median {stats['surround'][2]:.1f} m | "
              f"face differential: median {np.median(diff):.1f} m, "
              f"p90 {np.percentile(diff, 90):.1f} m")
        shown = np.where(ok, mag, np.nan)
        im = ax.imshow(shown, vmin=0, vmax=30, cmap="Blues",
                       extent=(cx[0], cx[-1], cy[-1], cy[0]))
        bad = np.where(~ok & np.isfinite(pk), 1.0, np.nan)
        ax.imshow(bad, cmap=matplotlib.colors.ListedColormap(["#e8d8d3"]),
                  extent=(cx[0], cx[-1], cy[-1], cy[0]), vmin=0, vmax=1)
        r = plt.Rectangle((box[1].start, box[0].start),
                          box[1].stop - box[1].start, box[0].stop - box[0].start,
                          fill=False, edgecolor="#eb6834", lw=1.5)
        ax.add_patch(r)
        ax.set_title(f"orbit {orbit} · {da} → {db_} ({role})", fontsize=10, loc="left")
        ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=axes, shrink=0.6, label="apparent shift (m), correlated windows"
                 " — pink = decorrelated")
    fig.suptitle("Speckle offset tracking, last pre-event pairs vs reference pairs",
                 fontsize=12, x=0.42)
    fig.savefig(os.path.join(FIGS, "offset_tracking.png"), dpi=160)
    plt.close(fig)
    print(f"fig -> {FIGS}/offset_tracking.png")


if __name__ == "__main__":
    main()
