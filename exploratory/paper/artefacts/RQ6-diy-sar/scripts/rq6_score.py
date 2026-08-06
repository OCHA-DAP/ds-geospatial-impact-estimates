"""RQ6 step 2 — score the DIY S1 amplitude-change product against CEMS.

Reads the z_*.tif tiles from rq6_gee_export.py and produces:
  1. Building-level threshold sweep: sample zmax at Overture centroids (gold building_flags),
     flag at z >= t, dual-anchor P/R vs CEMS {2,3} (r=10 m) in the Caraballeda area — the
     region comparable to the RQ5 quad frontier (same 1,455 CEMS points). Full curve, no
     tuning -> no leakage; overlay on the RQ5 frontier.
  2. Object-level post-processing sweep (t, min cluster size s): connected components on the
     z>=t mask, component centroids = detections, scored dual-anchor. TUNED on the west half
     of the Caraballeda strip, EVALUATED on the held-out east half (spatial holdout per
     DESIGN.md).
  3. Negative controls: flag rate (share of buildings with z >= t) in the Caracas & Santa Cruz
     CEMS areas vs Caraballeda, at representative thresholds — the RQ2c density-mirror contrast.

Run: uv run --group etl --with rasterio --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ6-diy-sar/scripts/rq6_score.py
"""
from __future__ import annotations
import glob, io, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import ndimage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
FIGS = os.path.join(HERE, "..", "figs")
os.makedirs(FIGS, exist_ok=True)
POS = (2, 3)
R = 10
THRESH = np.round(np.arange(1.0, 6.01, 0.25), 2)
MIN_SIZES = (1, 3, 5, 10, 20)  # pixels (100 m2 each)


def buildings():
    import ocha_stratus as stratus
    b = stratus.load_blob_data(
        gp.S.blob_path("gold", "model=common", "adm0=VE", "building_flags.parquet"),
        stage="dev", container_name=gp.S.container)
    df = pd.read_parquet(io.BytesIO(b), columns=["id", "lon", "lat"])
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    return g.to_crs(gp.METRIC_CRS)


def sample_z(bld):
    """Max z across tiles at each building centroid (NaN = no coverage)."""
    z = np.full(len(bld), np.nan)
    xs, ys = bld.geometry.x.to_numpy(), bld.geometry.y.to_numpy()
    for tif in sorted(glob.glob(os.path.join(DATA, "z_*.tif"))):
        with rasterio.open(tif) as src:
            b = src.bounds
            m = (xs >= b.left) & (xs <= b.right) & (ys >= b.bottom) & (ys <= b.top)
            if not m.any():
                continue
            vals = np.array([v[0] for v in src.sample(zip(xs[m], ys[m]))], dtype=float)
            nod = src.nodata
            if nod is not None:
                vals[vals == nod] = np.nan
            z[m] = np.fmax(z[m], vals)
    return z


def area_geoms():
    ext = gp.cems_extent()
    latest = gp.to_metric(ext[ext.is_latest == True])  # noqa: E712
    return {n: s.geometry.make_valid().union_all() for n, s in latest.groupby("aoi_name")}


def pr(flagged_pts, cems_pts, r=R):
    nr, dr = gp.match_rate(cems_pts, flagged_pts, r)
    npc, dpc = gp.match_rate(flagged_pts, cems_pts, r)
    rec = nr / dr if dr else np.nan
    prec = npc / dpc if dpc else np.nan
    f1 = 2 * prec * rec / (prec + rec) if (prec or 0) + (rec or 0) > 0 else 0.0
    return prec, rec, f1


def main():
    bld = buildings()
    bld["z"] = sample_z(bld)
    areas = area_geoms()
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)][["geometry"]]

    # ---------- 1. building-level threshold curve, Caraballeda ----------
    car = areas["Caraballeda"]
    u = bld[bld.geometry.within(car) & bld.z.notna()]
    cpts = cems[cems.geometry.within(car)]
    print(f"Caraballeda universe: {len(u):,} buildings with z, {len(cpts):,} CEMS pts")
    rows = []
    for t in THRESH:
        f = u[u.z >= t]
        prec, rec, f1 = pr(f, cpts)
        rows.append(dict(thresh=t, n_flag=len(f), flag_pct=round(100 * len(f) / len(u), 1),
                         precision=round(prec, 3), recall=round(rec, 3), f1=round(f1, 3)))
    curve = pd.DataFrame(rows)
    curve.to_csv(os.path.join(HERE, "..", "rq6_curve.csv"), index=False)
    print(curve.to_string(index=False))

    # ---------- 2. object-level (t, min size), spatial holdout ----------
    xmid = u.geometry.x.median()  # west = tune, east = test
    tune_g, test_g = u[u.geometry.x < xmid], u[u.geometry.x >= xmid]
    c_tune = cpts[cpts.geometry.x < xmid]
    c_test = cpts[cpts.geometry.x >= xmid]

    def objects(t, s):
        """Component centroids (metric points) over all Caraballeda tiles."""
        pts = []
        for tif in sorted(glob.glob(os.path.join(DATA, "z_caraballeda*.tif"))):
            with rasterio.open(tif) as src:
                a = src.read(1)
                nod = src.nodata
                mask = np.isfinite(a) & (a >= t) if nod is None else (a != nod) & (a >= t)
                lab, n = ndimage.label(mask)
                if n == 0:
                    continue
                sizes = ndimage.sum_labels(np.ones_like(lab), lab, index=np.arange(1, n + 1))
                keep = np.where(sizes >= s)[0] + 1
                if len(keep) == 0:
                    continue
                cy, cx = zip(*ndimage.center_of_mass(mask, lab, keep))
                xs, ys = rasterio.transform.xy(src.transform, cy, cx)
                pts.append(pd.DataFrame({"x": xs, "y": ys}))
        if not pts:
            return gpd.GeoDataFrame(geometry=[], crs=gp.METRIC_CRS)
        d = pd.concat(pts)
        return gpd.GeoDataFrame(geometry=gpd.points_from_xy(d.x, d.y), crs=gp.METRIC_CRS)

    grid = []
    for t in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        for s in MIN_SIZES:
            det = objects(t, s)
            det_t = det[det.geometry.x < xmid]
            prec, rec, f1 = pr(det_t, c_tune)
            grid.append(dict(thresh=t, min_px=s, n_obj=len(det),
                             tune_precision=round(prec, 3), tune_recall=round(rec, 3),
                             tune_f1=round(f1, 3)))
            print(f"  t={t} s={s}: {len(det)} objects  tune P={prec:.3f} R={rec:.3f} F1={f1:.3f}")
    gridf = pd.DataFrame(grid)
    best = gridf.sort_values("tune_f1", ascending=False).iloc[0]
    det = objects(best.thresh, int(best.min_px))
    det_e = det[det.geometry.x >= xmid]
    prec, rec, f1 = pr(det_e, c_test)
    print(f"\nBEST on tune (t={best.thresh}, s={int(best.min_px)}): "
          f"HELD-OUT east: P={prec:.3f} R={rec:.3f} F1={f1:.3f}")
    gridf.to_csv(os.path.join(HERE, "..", "rq6_objects_grid.csv"), index=False)
    with open(os.path.join(HERE, "..", "rq6_holdout_result.txt"), "w") as fh:
        fh.write(f"best tune config: t={best.thresh} min_px={int(best.min_px)} "
                 f"(tune F1={best.tune_f1})\nheld-out east: P={prec:.3f} R={rec:.3f} F1={f1:.3f}\n")

    # ---------- 3. negative controls ----------
    neg = []
    for nm in ("Caracas", "Santa Cruz", "Caraballeda"):
        if nm not in areas:
            continue
        g = areas[nm]
        ub = bld[bld.geometry.within(g) & bld.z.notna()]
        if len(ub) == 0:
            continue
        for t in (2.5, 3.0, 4.0):
            neg.append(dict(area=nm, thresh=t, n_bldg=len(ub),
                            flag_pct=round(100 * (ub.z >= t).mean(), 1)))
    negf = pd.DataFrame(neg).pivot(index="area", columns="thresh", values="flag_pct")
    negf.to_csv(os.path.join(HERE, "..", "rq6_negative_controls.csv"))
    print("\nflag %% by area (negative controls):\n", negf.to_string())

    # ---------- overlay on RQ5 frontier ----------
    rq5 = pd.read_csv(os.path.join(HERE, "..", "..", "RQ5-ensemble", "rq5_summary.csv"))
    on_quad = rq5[(rq5.members == "ms+impact+osu+uh") & (~rq5.rule.str.contains("quad"))]
    singles = rq5[rq5.rule.isin(["MS", "IMPACT", "OSU", "UH"])]
    fig, ax = plt.subplots(figsize=(7.5, 6))
    ax.plot(curve.recall, curve.precision, "-o", ms=3, c="black",
            label="DIY S1 amplitude z (threshold sweep)")
    for t in (2.0, 3.0, 4.0, 5.0):
        r_ = curve[curve.thresh == t]
        if len(r_):
            ax.annotate(f"z≥{t}", (r_.recall.iloc[0], r_.precision.iloc[0]),
                        textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.scatter(singles.recall_r10, singles.precision_r10, c="tab:blue", label="singles (RQ5)")
    ax.scatter(on_quad.recall_r10, on_quad.precision_r10, c="tab:red", marker="D",
               label="k-of-4 (RQ5)")
    for _, r_ in pd.concat([singles, on_quad]).iterrows():
        ax.annotate(r_.rule, (r_.recall_r10, r_.precision_r10),
                    textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_xlabel("recall (CEMS {2,3}, r=10 m)")
    ax.set_ylabel("precision")
    ax.set_title("RQ6 — DIY SAR threshold curve vs RQ5 frontier (Caraballeda)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq6_curve_vs_frontier.png"), dpi=130)
    print("wrote figs/rq6_curve_vs_frontier.png")


if __name__ == "__main__":
    main()
