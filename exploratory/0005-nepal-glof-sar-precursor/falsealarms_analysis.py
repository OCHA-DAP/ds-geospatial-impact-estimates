"""0005 step 4 — replay the morning-pass detector over every face-season.

Detector (the one that fired on the Langtang face): on morning (descending)
orbits, an alarm is >=3 CONSECUTIVE monsoon acquisitions with adjusted
climatology z <= -2, where
  z      = (VV - mean of other years within +/-12 days of the same DOY) / std,
           leave-one-out over 2020-2026 so a tested year never sits in its own
           baseline, per face x orbit;
  z_adj  = z minus the same-date median z across all faces on that orbit —
           the fleet median plays the role the hand-picked control boxes played
           in the single-face analysis (removes region-wide weather).

A face-season = one face x one monsoon test window (Jun 1 - Aug 25; the source
face's 2026 alarm ran Jul 2 - Aug 19, comfortably inside it). The false-alarm
rate is the share of non-source face-seasons that alarm. The source face in
2026 is the positive control the detector must catch.

Run: uv run --group etl --with matplotlib python \
       exploratory/0005-nepal-glof-sar-precursor/falsealarms_analysis.py
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FIGS = os.path.join(HERE, "figs")
os.makedirs(FIGS, exist_ok=True)

DOY_WINDOW = 12
MIN_POOL = 10
ALARM_Z = -2.0
RUN_LEN = 3
TEST_YEARS = range(2022, 2027)
SEASON = (152, 237)  # Jun 1 - Aug 25 in DOY terms (non-leap; +/-1 day is immaterial)
MIN_FACE_DATE = 8  # faces required on a date before the fleet median is trusted

C_SRC, C_FLEET, INK2 = "#2a78d6", "#8698a3", "#576873"


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    faces = pd.read_csv(os.path.join(DATA, "fleet_faces.csv"))
    df = pd.read_csv(os.path.join(DATA, "fleet_timeseries.csv"), parse_dates=["t"])
    # The GLIMS polygons are whole glaciers; averaging over 10 km2 dilutes a
    # face-scale anomaly (the source glacier's own polygon scores -1.6 in 2026,
    # under the -2 alarm). The positive control must be the same 2x3 km source
    # box the single-face analysis used — run through the identical machinery.
    src = pd.read_csv(os.path.join(DATA, "s1_timeseries.csv"), parse_dates=["t"])
    src = src[(src.aoi == "source") & (src.t < pd.Timestamp(2026, 8, 26))]
    src = src.assign(face_id="SOURCE-BOX")[
        ["t", "orbit", "pass", "face_id", "vv_db", "vh_db", "n_pix"]
    ]
    df = pd.concat([df, src], ignore_index=True)
    faces = pd.concat(
        [faces, pd.DataFrame([{"face_id": "SOURCE-BOX", "name": "detachment box",
                               "area_km2": 6.2, "mean_elev": 4973, "slope_deg": 39.9,
                               "is_source": 1}])], ignore_index=True)
    df = df[df["pass"] == "DESCENDING"].copy()  # morning passes only
    full = df.groupby(["face_id", "orbit"])["n_pix"].transform("max")
    df = df[(df.n_pix >= 0.8 * full) & df.vv_db.notna()].copy()
    df["year"] = df.t.dt.year
    df["doy"] = df.t.dt.dayofyear
    df["date"] = df.t.dt.date
    # a face-orbit needs a real multi-year baseline to be testable at all
    ok = df.groupby(["face_id", "orbit"]).year.transform("nunique") >= 5
    df = df[ok]
    print(f"{df.face_id.nunique()} faces with usable morning-orbit series "
          f"(of {len(faces)} selected)")
    return df, faces


def loo_z(df: pd.DataFrame) -> pd.DataFrame:
    """Leave-one-out climatology z for every acquisition, per face x orbit."""
    out = []
    for (fid, orbit), g in df.groupby(["face_id", "orbit"]):
        v = g.sort_values("t").reset_index(drop=True)
        doy, yr, vv = v.doy.values, v.year.values, v.vv_db.values
        z = np.full(len(v), np.nan)
        for i in range(len(v)):
            dd = np.minimum(np.abs(doy - doy[i]), 365 - np.abs(doy - doy[i]))
            pool = (dd <= DOY_WINDOW) & (yr != yr[i])
            if pool.sum() < MIN_POOL:
                continue
            z[i] = (vv[i] - vv[pool].mean()) / vv[pool].std(ddof=1)
        v["z"] = z
        out.append(v)
    return pd.concat(out, ignore_index=True).dropna(subset=["z"])


def adjust(z: pd.DataFrame) -> pd.DataFrame:
    """Subtract the same-date fleet median z (per orbit) — the 'everyone else'
    control. Dates carried by too few faces are dropped, not guessed."""
    med = z.groupby(["orbit", "date"]).z.agg(["median", "size"])
    z = z.join(med, on=["orbit", "date"])
    z = z[z["size"] >= MIN_FACE_DATE].copy()
    z["z_adj"] = z.z - z["median"]
    return z


def worst_run(z: pd.DataFrame) -> pd.DataFrame:
    """Per face-season: the worst 'RUN_LEN consecutive acquisitions' statistic —
    the rolling max over RUN_LEN of z_adj, minimised over the season. Alarm
    when <= ALARM_Z (i.e. RUN_LEN acquisitions in a row all <= ALARM_Z)."""
    rows = []
    seas = z[(z.doy >= SEASON[0]) & (z.doy <= SEASON[1]) & z.year.isin(TEST_YEARS)]
    for (fid, year, orbit), g in seas.groupby(["face_id", "year", "orbit"]):
        v = g.sort_values("t").z_adj.values
        if len(v) < RUN_LEN + 1:
            continue
        stat = min(max(v[i:i + RUN_LEN]) for i in range(len(v) - RUN_LEN + 1))
        rows.append({"face_id": fid, "year": year, "orbit": orbit,
                     "n_acq": len(v), "run_stat": stat})
    per_orbit = pd.DataFrame(rows)
    # face-season alarms if ANY of its morning orbits alarms
    agg = per_orbit.groupby(["face_id", "year"]).run_stat.min().reset_index()
    agg["alarm"] = agg.run_stat <= ALARM_Z
    return agg


def fig_runstat(res: pd.DataFrame, faces: pd.DataFrame) -> None:
    src_ids = {"SOURCE-BOX"}  # blue = the detachment box itself, nothing else
    fig, ax = plt.subplots(figsize=(9, 4.5))
    rng = np.random.default_rng(0)
    for i, year in enumerate(sorted(res.year.unique())):
        g = res[res.year == year]
        x = i + rng.uniform(-0.16, 0.16, len(g))
        fleet = ~g.face_id.isin(src_ids)
        ax.plot(x[fleet.values], g.run_stat[fleet], "o", color=C_FLEET, ms=5,
                alpha=0.75, mew=0)
        for xv, rv in zip(x[~fleet.values], g.run_stat[~fleet]):
            ax.plot(xv, rv, "o", color=C_SRC, ms=9, zorder=5)
            if year == 2026:
                ax.annotate("detachment box,\ncollapse season", (xv, rv),
                            color=C_SRC, fontsize=8.5,
                            xytext=(-105, -6), textcoords="offset points")
    deep = res[(res.year == 2026) & (res.run_stat < -6) & ~res.face_id.isin(src_ids)]
    for _, r in deep.iterrows():
        ax.annotate("uncollapsed face,\nsame drainage (Tibet side)",
                    (4, r.run_stat), color=INK2, fontsize=8.5,
                    xytext=(-140, 8), textcoords="offset points")
    ax.axhline(ALARM_Z, color="#b3402f", lw=1.2, ls="--")
    ax.text(-0.45, ALARM_Z - 0.12, "alarm threshold", color="#b3402f",
            fontsize=8.5, va="top")
    ax.set_xticks(range(len(sorted(res.year.unique()))))
    ax.set_xticklabels(sorted(res.year.unique()))
    ax.set_ylabel(f"worst {RUN_LEN}-in-a-row z (adjusted)")
    ax.set_title("Replaying the morning-pass detector on every steep glacier face — "
                 "grey: fleet, blue: the detachment box", fontsize=11, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#0b0b0b", alpha=0.08)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "falsealarm_runstat.png"), dpi=160)
    plt.close(fig)


def main() -> None:
    df, faces = load()
    z = adjust(loo_z(df))
    res = worst_run(z)
    src_ids = set(faces[faces.is_source == 1].face_id)
    res["is_source"] = res.face_id.isin(src_ids)

    hit = res[res.is_source & (res.year == 2026)]
    print("\n== positive control (source face, 2026) ==")
    print(hit.to_string(index=False) if len(hit) else "MISSING — source face not testable")

    fleet = res[~res.is_source | (res.year != 2026)]
    print(f"\n== fleet face-seasons {min(TEST_YEARS)}-{max(TEST_YEARS)} ==")
    n_alarm = int(fleet.alarm.sum())
    print(f"{len(fleet)} face-seasons, {n_alarm} alarms "
          f"-> false-alarm rate {100 * n_alarm / len(fleet):.1f}% per face-season")
    if n_alarm:
        alarms = fleet[fleet.alarm].merge(faces, on="face_id")
        print(alarms[["face_id", "name", "year", "run_stat", "area_km2",
                      "mean_elev"]].round(2).to_string(index=False))
    print("\nper-year alarm counts (fleet):")
    print(fleet.groupby("year").agg(faces=("face_id", "size"),
                                    alarms=("alarm", "sum")).to_string())
    print("\n== threshold sweep (fleet false-alarm rate vs catching the source box) ==")
    src26 = res[(res.face_id == "SOURCE-BOX") & (res.year == 2026)].run_stat
    src_stat = float(src26.iloc[0]) if len(src26) else float("nan")
    for thr in (-1.5, -2.0, -2.5, -3.0):
        fa = 100 * (fleet.run_stat <= thr).mean()
        caught = "catches" if src_stat <= thr else "MISSES"
        print(f"  threshold {thr:+.1f}: fleet rate {fa:4.1f}%  |  {caught} "
              f"the source box (stat {src_stat:+.2f})")
    fig_runstat(res, faces)
    print(f"\nfig -> {FIGS}/falsealarm_runstat.png")


if __name__ == "__main__":
    main()
