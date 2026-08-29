"""0005 step 2 — analyse the extracts from extract.py; prints numbers, saves figs/.

Logic:
  * Scar: threshold the post-event orbit-85 z map (|z| >= 3) to locate the actual
    detachment/runout, and report where it sits relative to the published coords.
  * Climatology: per orbit x AOI x pol, score each 2026 acquisition against prior
    years' (2020-25) acquisitions within +/-12 days of the same day-of-year:
    z_clim = (dB - mean_prior) / std_prior. A precursor = source-box z_clim
    departing while the controls stay put.
  * Pixel-level: inside the source box, per pre-event acquisition, the fraction of
    scar-mask pixels with z >= 2 vs the same fraction outside the mask (same box,
    same weather) — sensitive to change too small to move the whole-box mean.

Run: uv run --group etl --with rasterio,matplotlib python \
       exploratory/0005-nepal-glof-sar-precursor/analysis.py
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import rasterio.transform
import rasterio.warp
from rasterio.windows import from_bounds

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FIGS = os.path.join(HERE, "figs")
os.makedirs(FIGS, exist_ok=True)

EVENT = dt.datetime(2026, 8, 26, 2, 52, 10)
PUBLISHED = {"petley-early": (85.52515, 28.28532), "petley-blog": (85.5194, 28.2765)}
SOURCE_BOX = (85.512, 28.269, 85.533, 28.293)  # lon/lat, matches extract.py
DOY_WINDOW = 12  # days either side when pooling prior years
SCAR_Z = 3.0  # |z| defining the post-event scar
PIX_Z = 2.0  # per-pixel anomaly threshold for the pre-event fraction series

C = {"source": "#2a78d6", "control_w": "#eb6834", "control_e": "#1baf7a"}
LABEL = {"source": "Source (detachment face)", "control_w": "Control W", "control_e": "Control E"}


def load_timeseries() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(DATA, "s1_timeseries.csv"), parse_dates=["t"])
    # keep acquisitions that actually cover the box (burst edges leave slivers)
    full = df.groupby(["aoi", "orbit"])["n_pix"].transform("max")
    kept = df[(df.n_pix >= 0.8 * full) & df.vv_db.notna()].copy()
    dropped = len(df) - len(kept)
    print(f"timeseries: {len(kept)} rows kept, {dropped} partial/empty dropped")
    kept["doy"] = kept.t.dt.dayofyear
    kept["year"] = kept.t.dt.year
    return kept


def climatology_z(df: pd.DataFrame) -> pd.DataFrame:
    """z of each 2026 acquisition vs prior-year same-season acquisitions."""
    rows = []
    for (orbit, aoi), g in df.groupby(["orbit", "aoi"]):
        cur = g[g.year == 2026]
        ref = g[g.year < 2026]
        for _, r in cur.iterrows():
            d = np.minimum(np.abs(ref.doy - r.doy), 365 - np.abs(ref.doy - r.doy))
            pool = ref[d <= DOY_WINDOW]
            if len(pool) < 10:
                raise RuntimeError(
                    f"orbit {orbit} {aoi} doy {r.doy}: only {len(pool)} baseline acqs"
                )
            rec = {"t": r.t, "orbit": orbit, "aoi": aoi, "n_ref": len(pool)}
            for pol in ("vv_db", "vh_db"):
                rec[f"z_{pol[:2]}"] = (r[pol] - pool[pol].mean()) / pool[pol].std(ddof=1)
            rows.append(rec)
    return pd.DataFrame(rows).sort_values("t")


def divergence_onset(df: pd.DataFrame) -> pd.DataFrame:
    """Face-specific anomaly: d = source VV - mean(controls VV) per acquisition,
    scored against prior years' d at the same day-of-year (+/-DOY_WINDOW).
    Removes valley-wide weather; what is left is specific to the source face."""
    wide = df.pivot_table(index=["t", "orbit", "year", "doy"], columns="aoi",
                          values="vv_db").reset_index()
    wide["d"] = wide.source - (wide.control_w + wide.control_e) / 2
    rows = []
    for orbit, g in wide.groupby("orbit"):
        cur, ref = g[g.year == 2026], g[g.year < 2026]
        for _, r in cur.iterrows():
            dd = np.minimum(np.abs(ref.doy - r.doy), 365 - np.abs(ref.doy - r.doy))
            pool = ref[dd <= DOY_WINDOW]
            if len(pool) < 10:
                raise RuntimeError(f"orbit {orbit} doy {r.doy}: thin baseline ({len(pool)})")
            rows.append({"t": r.t, "orbit": orbit, "d_db": r.d,
                         "z_d": (r.d - pool.d.mean()) / pool.d.std(ddof=1)})
    out = pd.DataFrame(rows).sort_values("t")
    print("\n== source-minus-controls divergence (VV), 2026 pre-event ==")
    for orbit, g in out[out.t < EVENT].groupby("orbit"):
        run = g[g.z_d <= -2]
        onset = None
        # onset = first acquisition of the longest-suffix run of z_d <= -2
        for _, r in g.iterrows():
            if r.z_d <= -2 and onset is None:
                onset = r.t
            elif r.z_d > -2:
                onset = None
        n_low = (g.z_d <= -2).sum()
        print(f"orbit {orbit}: {n_low}/{len(g)} acqs at z<=-2; "
              f"sustained from {onset:%Y-%m-%d}" if onset is not None
              else f"orbit {orbit}: {n_low}/{len(g)} acqs at z<=-2; no sustained run")
    return out


def fig_divergence(dv: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4))
    marker = {19: "o", 85: "s", 121: "^"}
    for orbit, g in dv.groupby("orbit"):
        local = "06:03" if orbit in (19, 121) else "18:06"
        ax.plot(g.t, g.z_d, color=C["source"] if orbit != 85 else "#1baf7a", lw=2,
                marker=marker[orbit], ms=5, label=f"orbit {orbit} ({local} local)")
    ax.axhspan(-2, 2, color="#0b0b0b", alpha=0.05, lw=0)
    ax.axvline(EVENT, color="#52514e", lw=1, ls="--")
    ax.annotate("collapse Aug 26", xy=(EVENT, ax.get_ylim()[0]), fontsize=8,
                color="#52514e", xytext=(-70, 8), textcoords="offset points")
    ax.set_ylabel("z of (source − controls) vs 2020–25")
    ax.set_title("Face-specific VV divergence — morning (descending) vs evening "
                 "(ascending) passes, 2026", fontsize=11, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#0b0b0b", alpha=0.08)
    ax.legend(frameon=False, fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "divergence_z.png"), dpi=160)
    plt.close(fig)


def scar_mask_and_report():
    """Threshold the post-event z map; return (mask within source box, transform)."""
    with rasterio.open(os.path.join(DATA, "scar_z_orbit85.tif")) as src:
        l, b, r, t = rasterio.warp.transform_bounds("EPSG:4326", src.crs, *SOURCE_BOX)
        win = from_bounds(l, b, r, t, src.transform)
        z_box = src.read(1, window=win)
        z_all = src.read(1)
        px_km2 = abs(src.transform.a * src.transform.e) / 1e6
        scar_all = np.nansum(np.abs(z_all) >= SCAR_Z) * px_km2
        mask = np.abs(z_box) >= SCAR_Z
        scar_box = mask.sum() * px_km2
        print(
            f"scar (|z|>={SCAR_Z}): {scar_all:.2f} km2 in the wide map, "
            f"{scar_box:.2f} km2 inside the source box "
            f"({100 * scar_box / max(scar_all, 1e-9):.0f}% of total)"
        )
        # centroid of scar pixels inside the box, back to lon/lat
        if not mask.any():
            raise RuntimeError("no scar pixels inside the source box — AOI misplaced?")
        rr, cc = np.nonzero(mask)
        wt = src.window_transform(win)
        xs, ys = rasterio.transform.xy(wt, rr, cc)
        cx, cy = np.mean(xs), np.mean(ys)
        lon, lat = rasterio.warp.transform(src.crs, "EPSG:4326", [cx], [cy])
        print(f"scar centroid in box: {lat[0]:.5f}N {lon[0]:.5f}E")
        for name, (plon, plat) in PUBLISHED.items():
            dkm = np.hypot((plon - lon[0]) * 97.9, (plat - lat[0]) * 110.9)
            print(f"  vs published {name} ({plat}, {plon}): {dkm:.2f} km")
        return mask, z_all, src.bounds, src.crs


def preevent_fraction(mask: np.ndarray) -> pd.DataFrame:
    """Per pre-event acquisition: share of z>=PIX_Z pixels inside vs outside scar."""
    rows = []
    for path in sorted(glob.glob(os.path.join(DATA, "pre_z_orbit*.tif"))):
        m = re.search(r"orbit(\d+)_(\d{8}T\d{4})", path)
        orbit, stamp = int(m.group(1)), dt.datetime.strptime(m.group(2), "%Y%m%dT%H%M")
        with rasterio.open(path) as src:
            z = src.read(1)
        if z.shape != mask.shape:  # grids may differ by one row/col of padding
            h, w = min(z.shape[0], mask.shape[0]), min(z.shape[1], mask.shape[1])
            z, mk = z[:h, :w], mask[:h, :w]
        else:
            mk = mask
        valid = np.isfinite(z)
        rows.append(
            {
                "t": stamp,
                "orbit": orbit,
                "frac_in": np.mean(z[mk & valid] >= PIX_Z),
                "frac_out": np.mean(z[~mk & valid] >= PIX_Z),
                "mean_in": np.mean(z[mk & valid]),
                "mean_out": np.mean(z[~mk & valid]),
            }
        )
    return pd.DataFrame(rows).sort_values("t")


def fig_climatology(zc: pd.DataFrame) -> None:
    orbits = sorted(zc.orbit.unique())
    fig, axes = plt.subplots(len(orbits), 1, figsize=(9, 8), sharex=True, sharey=True)
    for ax, orbit in zip(axes, orbits):
        sub = zc[zc.orbit == orbit]
        for aoi in ("source", "control_w", "control_e"):
            g = sub[sub.aoi == aoi]
            ax.plot(g.t, g.z_vv, color=C[aoi], lw=2, marker="o", ms=4, label=LABEL[aoi])
        ax.axhspan(-2, 2, color="#0b0b0b", alpha=0.05, lw=0)
        ax.axvline(EVENT, color="#52514e", lw=1, ls="--")
        ax.set_ylabel(f"orbit {orbit}\nVV z vs 2020–25")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#0b0b0b", alpha=0.08)
    axes[0].legend(frameon=False, ncol=3, loc="upper left", fontsize=9)
    axes[0].set_title(
        "Sentinel-1 VV backscatter, 2026 vs same-season prior years — "
        "source face vs controls", fontsize=11, loc="left"
    )
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    axes[-1].annotate("collapse\nAug 26", xy=(EVENT, axes[-1].get_ylim()[0]),
                      fontsize=8, color="#52514e", xytext=(5, 5), textcoords="offset points")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "climatology_z.png"), dpi=160)
    plt.close(fig)


def fig_raw_series(df: pd.DataFrame) -> None:
    """Raw VV dB, all years greyed, 2026 in color — one panel per orbit, source box."""
    orbits = sorted(df.orbit.unique())
    fig, axes = plt.subplots(len(orbits), 1, figsize=(9, 8), sharex=True)
    for ax, orbit in zip(axes, orbits):
        g = df[(df.orbit == orbit) & (df.aoi == "source")]
        for yr, gy in g.groupby("year"):
            gy = gy.sort_values("doy")
            if yr < 2026:
                ax.plot(gy.doy, gy.vv_db, color="#0b0b0b", alpha=0.15, lw=1)
            else:
                ax.plot(gy.doy, gy.vv_db, color=C["source"], lw=2, marker="o", ms=4)
        ax.axvline(EVENT.timetuple().tm_yday, color="#52514e", lw=1, ls="--")
        ax.set_ylabel(f"orbit {orbit}\nVV dB")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#0b0b0b", alpha=0.08)
    axes[0].set_title(
        "Source box, raw VV backscatter by day-of-year — 2026 (blue) over 2020–25 (grey)",
        fontsize=11, loc="left",
    )
    axes[-1].set_xlabel("day of year")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "raw_vv_doy.png"), dpi=160)
    plt.close(fig)


def fig_scar(z_all: np.ndarray, bounds, crs) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 7))
    im = ax.imshow(
        np.abs(z_all), vmin=0, vmax=6, cmap="Blues",
        extent=(bounds.left, bounds.right, bounds.bottom, bounds.top),
    )
    for name, (plon, plat) in PUBLISHED.items():
        x, y = rasterio.warp.transform("EPSG:4326", crs, [plon], [plat])
        ax.plot(x, y, "x", color="#e34948", ms=10, mew=2)
        ax.annotate(name, (x[0], y[0]), color="#e34948", fontsize=8,
                    xytext=(6, 4), textcoords="offset points")
    sl, sb, sr, st = rasterio.warp.transform_bounds("EPSG:4326", crs, *SOURCE_BOX)
    ax.add_patch(plt.Rectangle((sl, sb), sr - sl, st - sb, fill=False,
                               edgecolor="#eb6834", lw=1.5))
    ax.set_title("Post-event |z| (orbit 85, 2026-08-28 vs Jun–Aug 2026) — scar + runout",
                 fontsize=11, loc="left")
    ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=ax, shrink=0.7, label="|z|")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "scar_map.png"), dpi=160)
    plt.close(fig)


def fig_fraction(fr: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4))
    marker = {19: "o", 85: "s", 121: "^"}
    for orbit, g in fr.groupby("orbit"):
        ax.plot(g.t, 100 * g.frac_in, color=C["source"], lw=2,
                marker=marker[orbit], ms=6, label=f"scar pixels, orbit {orbit}")
        ax.plot(g.t, 100 * g.frac_out, color="#0b0b0b", alpha=0.3, lw=1.5,
                marker=marker[orbit], ms=4, label=f"rest of box, orbit {orbit}")
    ax.axvline(EVENT, color="#52514e", lw=1, ls="--")
    ax.set_ylabel(f"% pixels with z ≥ {PIX_Z}")
    ax.set_title("Pre-event anomalous-pixel share inside the future scar vs around it",
                 fontsize=11, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#0b0b0b", alpha=0.08)
    ax.legend(frameon=False, fontsize=8, ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "preevent_fraction.png"), dpi=160)
    plt.close(fig)


def main() -> None:
    df = load_timeseries()
    zc = climatology_z(df)
    pre = zc[zc.t < EVENT]
    print("\n== climatology z (VV), last 5 pre-event acquisitions per orbit ==")
    for orbit, g in pre[pre.aoi == "source"].groupby("orbit"):
        tail = g.sort_values("t").tail(5)
        print(f"orbit {orbit}: " + "  ".join(
            f"{r.t:%m-%d}:{r.z_vv:+.1f}" for r in tail.itertuples()))
    print("\nmax |z_vv| pre-event by AOI (2026 Jun 1 on):")
    seas = pre[pre.t >= dt.datetime(2026, 6, 1)]
    print(seas.groupby("aoi").z_vv.agg(["mean", "min", "max"]).round(2))

    dv = divergence_onset(df)
    mask, z_all, bounds, crs = scar_mask_and_report()
    fr = preevent_fraction(mask)
    print("\n== anomalous-pixel share inside future scar (z >= 2) ==")
    print(fr.assign(t=fr.t.dt.strftime("%m-%d"),
                    frac_in=(100 * fr.frac_in).round(1),
                    frac_out=(100 * fr.frac_out).round(1),
                    mean_in=fr.mean_in.round(2),
                    mean_out=fr.mean_out.round(2)).to_string(index=False))

    fig_climatology(zc)
    fig_raw_series(df)
    fig_divergence(dv)
    fig_scar(z_all, bounds, crs)
    fig_fraction(fr)
    print(f"\nfigs -> {FIGS}")


if __name__ == "__main__":
    main()
