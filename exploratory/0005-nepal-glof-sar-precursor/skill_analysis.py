"""0005 step 9 — threshold-free skill analysis.

The history test scored events pass/fail against -2 sigma, but that threshold
was picked by eyeballing the Langtang case itself — circular. This reframes
the whole record without any privileged threshold:

  * per dataset, the NULL distribution of the detector statistic (worst
    3-consecutive adjusted z in the test window) over every unit-season with
    no collapse;
  * each positive placed in its own dataset's null as a rank and an empirical
    p-value, p = (1 + #null <= observed) / (1 + N)  (Laplace, one-sided);
  * Fisher's combination of the two independent positives at operational scale;
  * the full threshold sweep as a curve: pooled false-alarm rate vs which
    positives a given threshold would have caught.

Datasets (all series already extracted by earlier steps; stats recomputed here
with one shared implementation):
  langtang-facets  facet_ts_langtang.csv           Jun-Aug window, 2020-26
  sedongpu-tiles   retest_ts_sedongpu.csv (+ hist fleet)  90-d pre-event window
  chamoli / marmolada / aru1 / aru2 fleets         extra null mass only

Positives at operational (computed-unit) scale:
  Langtang 2026 on its auto-facet; Sedongpu 2018 as the min-over-tiles year
  statistic (the "watch the basin" comparison is min-vs-min across years).

Run: uv run --group etl --with matplotlib python \
       exploratory/0005-nepal-glof-sar-precursor/skill_analysis.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

RUN_LEN, DOY_WIN, MIN_POOL = 3, 12, 10


def prep(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["t"])
    if "facet_id" in df.columns:  # facets_prototype.py names the unit column differently
        df = df.rename(columns={"facet_id": "face_id"})
    full = df.groupby(["face_id", "orbit"])["n_pix"].transform("max")
    df = df[(df.n_pix >= 0.8 * full) & df.vv_db.notna()].copy()
    df["year"], df["doy"] = df.t.dt.year, df.t.dt.dayofyear
    df["date"] = df.t.dt.date
    return df[df.groupby(["face_id", "orbit"]).year.transform("nunique") >= 3]


def loo_z(df: pd.DataFrame) -> pd.DataFrame:
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


def unit_season_stats(units: pd.DataFrame, fleet: pd.DataFrame, doys: tuple[int, int],
                      min_face_date: int, wrap_to_later: bool = False) -> pd.DataFrame:
    """Worst 3-run adjusted-z per unit-season inside the DOY window."""
    zu, zf = loo_z(units), loo_z(fleet)
    med = zf.groupby(["orbit", "date"]).z.agg(["median", "size"])
    zu = zu.join(med, on=["orbit", "date"])
    zu = zu[zu["size"] >= min_face_date].copy()
    zu["z_adj"] = zu.z - zu["median"]
    w0, w1 = doys
    m = ((zu.doy > w0) & (zu.doy <= w1)) if w0 < w1 else ((zu.doy > w0) | (zu.doy <= w1))
    seas = zu[m].copy()
    if w0 > w1 and wrap_to_later:
        seas.loc[seas.doy > w0, "year"] += 1
    rows = []
    for (fid, year, orbit), g in seas.groupby(["face_id", "year", "orbit"]):
        v = g.sort_values("t").z_adj.values
        if len(v) >= RUN_LEN:
            rows.append({"face_id": fid, "year": year,
                         "stat": min(max(v[i:i + RUN_LEN]) for i in range(len(v) - RUN_LEN + 1))})
    return pd.DataFrame(rows).groupby(["face_id", "year"]).stat.min().reset_index()


def emp_p(observed: float, null: np.ndarray) -> float:
    return (1 + (null <= observed).sum()) / (1 + len(null))


def main() -> None:
    # ---- Langtang at facet scale ------------------------------------------
    fa = prep(os.path.join(DATA, "facet_ts_langtang.csv"))
    target = "F00182"
    res = unit_season_stats(fa, fa[fa.face_id != target], (152, 237), 8)
    pos_lt = float(res[(res.face_id == target) & (res.year == 2026)].stat.iloc[0])
    null_lt = res[~((res.face_id == target) & (res.year == 2026))].stat.values
    p_lt = emp_p(pos_lt, null_lt)
    rank_lt = int((null_lt <= pos_lt).sum()) + 1
    print(f"langtang facet 2026: stat {pos_lt:+.2f}, rank {rank_lt}/{len(null_lt) + 1} "
          f"unit-seasons, empirical p = {p_lt:.4f}")

    # ---- Sedongpu at tile scale (min-over-tiles per year vs same in other years)
    tiles = prep(os.path.join(DATA, "retest_ts_sedongpu.csv"))
    fleet = prep(os.path.join(DATA, "hist_ts_sedongpu.csv"))
    fleet = fleet[fleet.face_id != "SOURCE-BOX"]
    ev = pd.Timestamp("2018-10-16")
    w = ((ev - pd.Timedelta(days=90)).dayofyear, ev.dayofyear)
    res_t = unit_season_stats(tiles, fleet, w, 6)
    ymin = res_t.groupby("year").stat.min()
    pos_sp = float(ymin.loc[2018])
    null_sp = ymin.drop(2018).values
    p_sp = emp_p(pos_sp, null_sp)
    print(f"sedongpu min-over-tiles 2018: stat {pos_sp:+.2f}, rank "
          f"{int((null_sp <= pos_sp).sum()) + 1}/{len(null_sp) + 1} years, "
          f"empirical p = {p_sp:.3f}")
    # per-tile-season null for the pooled sweep (event-year tiles excluded)
    null_sp_units = res_t[res_t.year != 2018].stat.values

    # ---- Fisher combination of the two independent positives --------------
    from scipy import stats as sstats

    chi2 = -2 * (np.log(p_lt) + np.log(p_sp))
    p_comb = 1 - sstats.chi2.cdf(chi2, df=4)
    print(f"\nFisher combination of the two positives: chi2(4) = {chi2:.1f}, "
          f"p = {p_comb:.4f}")
    print("(read as: probability of both collapse seasons ranking this extreme "
          "in their own nulls if the detector carried no signal)")

    # ---- extra null mass from the other fleets (no positives) -------------
    extra = []
    for name, event, wrap in [("chamoli", "2021-02-07", True),
                              ("marmolada", "2022-07-03", False),
                              ("aru1", "2016-07-17", False)]:
        f = prep(os.path.join(DATA, f"hist_ts_{name}.csv"))
        f = f[f.face_id != "SOURCE-BOX"]
        e = pd.Timestamp(event)
        w = ((e - pd.Timedelta(days=90)).dayofyear, e.dayofyear)
        r = unit_season_stats(f, f, w, 6, wrap_to_later=wrap)
        extra.append(r.stat.values)
        print(f"{name} fleet null: n={len(r)}, min {r.stat.min():+.2f}")

    # ---- threshold sweep, no privileged value -----------------------------
    pooled_null = np.concatenate([null_lt, null_sp_units] + extra)
    print(f"\npooled null: {len(pooled_null)} unit-seasons across 5 regions")
    print(f"{'thr':>6} {'FA rate':>8} {'langtang':>9} {'sedongpu':>9}")
    for thr in np.arange(-1.25, -3.26, -0.25):
        fa_rate = 100 * (pooled_null <= thr).mean()
        print(f"{thr:+6.2f} {fa_rate:7.2f}% {'caught' if pos_lt <= thr else '·':>9} "
              f"{'caught' if pos_sp <= thr else '·':>9}")
    both = max(pos_lt, pos_sp)
    print(f"\nloosest threshold catching both positives: {both:+.2f} "
          f"-> pooled false-alarm rate {100 * (pooled_null <= both).mean():.2f}% "
          f"per unit-season")


if __name__ == "__main__":
    main()
