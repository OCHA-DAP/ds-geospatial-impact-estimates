"""RQ8c — reference-basis sensitivity for @fig-bestf1's ten predictors (frozen, no refits).

Everything is held fixed: predictors are the RQ8 OOF scores / gold flags dumped in
rq8_oof_scores_r10.parquet, operating points are the ones recorded in rq8_best_f1_r10.csv
(chosen once, against the paper's {2,3} basis). The ONLY thing that varies is which CEMS
grades define the reference:
    destroyed {3}  ·  dmg+destroyed {2,3} (the paper)  ·  incl_possibly {1,2,3}
Refitting per basis would let our constructions adapt to each target while the shipped
products cannot; frozen scores isolate the reference as the single moving part (and the
RQ9 CI script's rule applies: resample/reuse these scores, never refit).

Label rule identical to rq8_learned_fusion.py: a building is positive iff its centroid is
within 10 m of a CEMS point of an included class. Recall is building-denominator (share of
positive buildings flagged), matching rq8_best_f1 — NOT rq2q's point-denominator recall.

The CSV's rounded `threshold` column moves one building across the cut for the learned
scores, so each frozen operating point is recovered exactly from its `n_flags` instead
(the n-th largest score).

VERIFICATION ANCHOR: the dmg+destroyed rows must reproduce rq8_best_f1_r10.csv exactly
(precision/recall/f1/n_flags, all ten predictors) or the script raises.

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8c_basis_sensitivity.py
"""
from __future__ import annotations
import os, sys

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
R = 10
BASES = {"destroyed": (3,), "dmg+destroyed": (2, 3), "incl_possibly": (1, 2, 3)}
PRODUCTS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]

d = pd.read_parquet(os.path.join(HERE, "..", "rq8_oof_scores_r10.parquet"))
ref = pd.read_csv(os.path.join(HERE, "..", "rq8_best_f1_r10.csv"))
nfl = ref.set_index("predictor").n_flags

bld = gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d.lon, d.lat), crs=4326)
bld = bld.to_crs(gp.METRIC_CRS)
bxy = np.c_[bld.geometry.x, bld.geometry.y]
cems = gp.to_metric(gp.cems_points())


def at_nflags(score, n):  # the frozen operating point, exactly n flags
    return score >= np.partition(score, -n)[-n]


votes = d[[f"flag_{p}" for p in PRODUCTS]].sum(axis=1).to_numpy()
predictors = {p: (d[f"flag_{p}"].to_numpy(dtype="float64") == 1) for p in PRODUCTS}
predictors["geography null (logistic)"] = at_nflags(d.null_logit.to_numpy(),
                                                    nfl["geography null (logistic)"])
predictors["geography null (rand. forest)"] = at_nflags(d.null_rf.to_numpy(),
                                                        nfl["geography null (rand. forest)"])
predictors["flat k-of-6 voting"] = votes >= 5  # integer score, no rounding issue
predictors["weighted fusion"] = at_nflags(d.fusion_logit.to_numpy(), nfl["weighted fusion"])

rows = []
for bname, classes in BASES.items():
    cp = cems[cems.damage_class.isin(classes)]
    dist, _ = cKDTree(np.c_[cp.geometry.x, cp.geometry.y]).query(bxy, k=1)
    y = (dist <= R).astype(int)
    npos = int(y.sum())
    print(f"[{bname}] classes {classes}: {len(cp):,} CEMS points -> {npos:,} positive buildings")
    for nm, mask in predictors.items():
        nflag = int(mask.sum())
        tp = int((mask & (y == 1)).sum())
        prec, rec = tp / max(nflag, 1), tp / max(npos, 1)
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        rows.append(dict(basis=bname, predictor=nm, n_flags=nflag, n_pos=npos,
                         precision=round(prec, 3), recall=round(rec, 3), f1=round(f1, 3)))

out = pd.DataFrame(rows)

chk = out[out.basis == "dmg+destroyed"].set_index("predictor")
bad = []
for _, r_ in ref.iterrows():
    got = chk.loc[r_.predictor]
    for c in ("precision", "recall", "f1", "n_flags"):
        if got[c] != r_[c]:
            bad.append(f"{r_.predictor}.{c}: got {got[c]}, frozen {r_[c]}")
if bad:
    raise SystemExit("ANCHOR FAILED — dmg+destroyed does not reproduce rq8_best_f1_r10.csv:\n  "
                     + "\n  ".join(bad))
print("anchor OK: dmg+destroyed reproduces rq8_best_f1_r10.csv exactly (all 10 predictors)")

out.to_csv(os.path.join(HERE, "..", "rq8c_basis_pr_r10.csv"), index=False)
print(out.pivot(index="predictor", columns="basis", values=["precision", "recall", "f1"])
      .to_string())
print("wrote rq8c_basis_pr_r10.csv")
