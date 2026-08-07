"""RQ7 round-2 replication — MapSwipe project 3248 (Catia La Mar round 2) vs 3179.

POST-FREEZE analysis (data collected 2026-07-15..2026-08-05, ingested 2026-08-07 as an
additive bronze partition). Round 2 re-served the IDENTICAL 3,482 res-11 task cells to a
fresh crowd of 728 volunteers at ~2.7x the vote depth (median 16 votes/task vs 6), but on
a redesigned 2-option instrument: 1 = "Yes" and 2 = "Not Sure", whose own description
absorbs "there is no damage" — the round-1 active-rejection answer (0 = "No") no longer
exists, so the frozen 71%-majority-No statistic is not re-testable by design.

What it computes (all deterministic; nothing here touches any frozen number):
  1. cell level  — majority-verdict distribution per round + the r1 x r2 crosstab;
  2. flag level  — the quantity the rq2i crowd adjustment actually consumes: the share of
     each product's CEMS-unmatched flags (gold centroids, r = 10 m, grades 2-3) whose
     task cell has majority "Yes", under each round's verdicts;
  3. reliability — variance decomposition of per-cell Yes-shares from the raw per-vote
     exports (binomial sampling noise vs real between-cell signal), the implied per-round
     reliabilities, and the noise-corrected (errors-in-variables) cross-round correlation
     of the underlying cell propensities;
  4. sensitivity — the implied movement of rq2i's as-delivered P_crowd_adj if round-2
     verdicts replaced round-1 in the strip. Computed FROM rq2i's frozen CSV row via the
     mechanism identity P_adj = (tp + U*conf)/N (never re-scoring anything): only the
     strip portion of conf changes, so conf' = conf + w*(conf2-conf1) with w = the
     strip's share of the product's covered unmatched flags. Rounded rq2i inputs give
     ~±0.002 slop; the swap also mixes two instruments (round 2 has no "No" option and a
     stricter "Yes"), so read it as a sensitivity bound, not a corrected value.

Writes: rq7_round2_replication.csv (tidy metric/value), rq7_round2_crosstab.csv,
        rq7_round2_padj_sensitivity.csv (per product).

Run: uv run --group etl python \
       exploratory/paper/artefacts/RQ7-mapswipe-validation/scripts/rq7_round2_replication.py
"""
from __future__ import annotations

import gzip
import io
import json
import os
import sys

import geopandas as gpd
import h3
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402
import ocha_stratus as stratus  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..")
ROUNDS = {"r1": "3179", "r2": "3248"}   # round 2 opted into EXPLICITLY (post-freeze)
R_MATCH = 10.0
POS = (2, 3)


def _blob(name_contains: str, project: str) -> bytes:
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    pref = gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE", f"project={project}")
    names = [b.name for b in cc.list_blobs(name_starts_with=pref) if name_contains in b.name]
    if len(names) != 1:
        raise RuntimeError(f"expected exactly one '{name_contains}' blob for "
                           f"project {project}, found {names}")
    return cc.download_blob(names[0]).readall()


def load_cells() -> pd.DataFrame:
    """Per-task vote shares + majority for both rounds, aligned on the h3 task id."""
    out = {}
    for rnd, pid in ROUNDS.items():
        t = pd.DataFrame([f["properties"] for f in json.loads(
            gzip.decompress(_blob("agg_results_by_task", pid)))["features"]])
        if "0_share" not in t.columns:   # 2-option round: derive the implicit "No" zeros
            t["0_count"] = t["total_count"] - t["1_count"] - t["2_count"]
            if (t["0_count"] < 0).any():
                raise RuntimeError(f"project {pid}: 0_count derivation invalid")
            t["0_share"] = t["0_count"] / t["total_count"]
        t = t.set_index("h3")
        t["majority"] = t[["0_share", "1_share", "2_share"]].to_numpy().argmax(axis=1)
        out[rnd] = t[["majority", "0_share", "1_share", "2_share", "total_count"]]
    if set(out["r1"].index) != set(out["r2"].index):
        raise RuntimeError("rounds do not cover identical task cells")
    return out["r1"].join(out["r2"], lsuffix="_r1", rsuffix="_r2")


FLAGS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
         "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}


def flag_level(cells: pd.DataFrame) -> pd.DataFrame:
    """The rq2i-mechanism quantity per product: confirmed share of the product's
    CEMS-unmatched flags that fall in the strip's cells, under each round's verdicts."""
    df = gp.building_flags(columns=["lon", "lat", *FLAGS.values()])
    df = df.assign(cell11=[h3.latlng_to_cell(la, lo, 11)
                           for la, lo in zip(df.lat, df.lon)])
    df = df[df["cell11"].isin(cells.index)]

    cems = gp.cems_points()
    cems = cems[cems.damage_class.isin(POS)]
    cm = cems.to_crs(gp.METRIC_CRS)
    cm = cm.set_geometry(cm.geometry.representative_point())

    rows = []
    for prod, col in FLAGS.items():
        sub = df[df[col].to_numpy(dtype="float64", na_value=0.0) == 1.0]
        fl = gpd.GeoDataFrame(sub[["cell11"]],
                              geometry=gpd.points_from_xy(sub.lon, sub.lat),
                              crs=4326).to_crs(gp.METRIC_CRS)
        near = gpd.sjoin_nearest(fl, cm[["geometry"]], how="left", distance_col="d")
        hit = (near.groupby(near.index)["d"].min() <= R_MATCH).values
        un = fl[~hit]
        m1 = un["cell11"].map(cells["majority_r1"])
        m2 = un["cell11"].map(cells["majority_r2"])
        rows.append({"product": prod, "flags_in_cells": len(fl),
                     "cems_matched": int(hit.sum()), "unmatched": len(un),
                     "unmatched_conf_share_r1": float((m1 == 1).mean()),
                     "unmatched_conf_share_r2": float((m2 == 1).mean())})
    return pd.DataFrame(rows).set_index("product")


def padj_sensitivity(fl: pd.DataFrame) -> pd.DataFrame:
    """Implied as-delivered P_crowd_adj under a round-2 swap, from rq2i's frozen CSV."""
    rq2i = pd.read_csv(os.path.join(OUT, "..", "RQ2-cems-footprint-points",
                                    "rq2i_per_aoi_scorecard.csv"))
    rq2i = (rq2i[rq2i.aoi == "ALL (as delivered)"]
            .drop_duplicates(subset="product").set_index("product"))
    rows = []
    for prod in fl.index:
        r = rq2i.loc[prod]
        tp = r.P_cems * r.n_flags
        unmatched = r.n_flags - tp
        covered = unmatched * r.crowd_cov_of_fps
        strip_cov = fl.loc[prod, "unmatched"]           # strip cells are all voted
        if covered <= 0 or strip_cov > covered * 1.02:  # 2% slop for rounded inputs
            raise RuntimeError(f"{prod}: strip covered flags ({strip_cov}) exceed "
                               f"total covered ({covered:.0f}) — frame mismatch")
        w = min(strip_cov / covered, 1.0)
        d_conf = (fl.loc[prod, "unmatched_conf_share_r2"]
                  - fl.loc[prod, "unmatched_conf_share_r1"])
        conf_new = r.fp_crowd_damaged + w * d_conf
        p_new = (tp + unmatched * conf_new) / r.n_flags
        rows.append({"product": prod, "P_crowd_adj_r1": r.P_crowd_adj,
                     "strip_share_of_covered_fps": round(w, 3),
                     "P_crowd_adj_r2swap": round(p_new, 3),
                     "delta": round(p_new - r.P_crowd_adj, 3)})
    return pd.DataFrame(rows).set_index("product")


def reliability() -> dict:
    """Moment-based variance decomposition from the raw per-vote exports."""
    shares = {}
    for rnd, pid in ROUNDS.items():
        v = pd.read_csv(io.BytesIO(_blob(f"results_{pid}.csv.gz", pid)),
                        compression="gzip")
        v["is_yes"] = (v["result"] == 1).astype(float)
        g = v.groupby("task_id")["is_yes"].agg(["mean", "count"])
        shares[rnd] = g.rename(columns={"mean": "s", "count": "n"})
    j = shares["r1"].join(shares["r2"], lsuffix="1", rsuffix="2", how="inner")
    if len(j) != 3482:
        raise RuntimeError(f"paired task count {len(j)} != 3,482 — join key drifted")
    out = {"paired_tasks": len(j),
           "votes_r1": int(shares["r1"].n.sum()), "votes_r2": int(shares["r2"].n.sum())}
    sig = {}
    for k in ("1", "2"):
        s, n = j[f"s{k}"], j[f"n{k}"]
        noise = float((s * (1 - s) / (n - 1)).mean())   # E[binomial var of a share]
        total = float(s.var())
        sig[k] = total - noise
        out[f"share_var_total_r{k}"] = total
        out[f"share_var_noise_r{k}"] = noise
        out[f"reliability_r{k}"] = sig[k] / total
    out["pearson_raw"] = float(j.s1.corr(j.s2))
    out["latent_correlation"] = float(j.s1.cov(j.s2) / np.sqrt(sig["1"] * sig["2"]))
    return out


def main() -> None:
    cells = load_cells()
    rows = [("paired_task_cells", len(cells)),
            ("median_votes_per_task_r1", float(cells["total_count_r1"].median())),
            ("median_votes_per_task_r2", float(cells["total_count_r2"].median()))]
    for rnd in ("r1", "r2"):
        m = cells[f"majority_{rnd}"]
        for v, lab in ((0, "no"), (1, "yes"), (2, "unsure")):
            rows.append((f"cell_majority_{lab}_share_{rnd}", float((m == v).mean())))

    ct = pd.crosstab(cells["majority_r1"], cells["majority_r2"])
    ct.index = [f"r1_{v}" for v in ct.index]
    ct.columns = [f"r2_{v}" for v in ct.columns]
    ct.to_csv(os.path.join(OUT, "rq7_round2_crosstab.csv"))

    fl = flag_level(cells)
    rows += [(f"ms_{k}", v) for k, v in fl.loc["MS"].items()]
    rel = reliability()
    rows += list(rel.items())

    res = pd.DataFrame(rows, columns=["metric", "value"])
    res.to_csv(os.path.join(OUT, "rq7_round2_replication.csv"), index=False)
    print(res.to_string(index=False))
    print("\ncrosstab (majority verdicts, 0=No 1=Yes 2=Unsure):")
    print(ct.to_string())

    sens = padj_sensitivity(fl).join(
        fl[["unmatched", "unmatched_conf_share_r1", "unmatched_conf_share_r2"]]
        .rename(columns={"unmatched": "strip_unmatched_flags"}))
    sens.to_csv(os.path.join(OUT, "rq7_round2_padj_sensitivity.csv"))
    print("\nP_crowd_adj sensitivity (as-delivered, round-2 verdicts swapped into strip):")
    print(sens.to_string())
    print("\nwrote rq7_round2_replication.csv, rq7_round2_crosstab.csv, "
          "rq7_round2_padj_sensitivity.csv")


if __name__ == "__main__":
    main()
