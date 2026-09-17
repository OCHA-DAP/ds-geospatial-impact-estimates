"""Compare the compact pipeline's rows with the oracle (artefacts/results.csv built from the
frozen per-RQ scripts). Every (region, lens, radius, predictor, metric) the pipeline produces
must exist in the oracle with the same value, except the declared, explained exceptions.

Usage: python check_against_oracle.py results_scorecards.csv [results_ranking.csv ...]
Exit 1 on any unexplained difference.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ORACLE = os.path.join(HERE, "..", "results_oracle_frozen.csv")  # the frozen scripts' final output (2026-09-14)
KEY = ["region", "lens", "radius", "predictor", "metric"]

# Known, explained differences between the pipeline and the frozen scripts. Each entry is a
# predicate over the merged row and a one-line reason; matching rows are reported, not failed.
EXCEPTIONS = [
    (lambda r: r.lens == "crowd" and r.metric == "fp_crowd_damaged" and r.source_oracle.endswith("rq2i_per_aoi_scorecard.csv"),
     "rq2i defined fp_crowd_damaged as confirmed / ALL unmatched flags; the pipeline uses confirmed / REVIEWED (rq5b's definition) everywhere"),
    (lambda r: r.lens == "crowd" and r.metric in ("crowd_cov", "P_crowd") and (r.source_oracle.endswith("rq2i_per_aoi_scorecard.csv") or r.source_oracle.endswith("rq5b_six_member.csv")) and abs(r.value_new - r.value_oracle) <= 0.011,
     "rq2i and rq5b took representative points after reprojecting to lon/lat (not in the metric frame, ADR-0030); 1-2 buildings change crowd cell "
     "(verified 2026-09-15 for 5-of-6: 469 vs 468 of 481 unmatched flags reviewed -> .98 vs .97)"),
    (lambda r: r.lens == "cells-agreement" and r.predictor == "weighted fusion",
     "fusion row is only produced with --with-fusion (frozen rq8 parquet)"),
    (lambda r: (r.lens == "cells" and r.metric in ("rho_null", "top20_null", "delta"))
               or (r.lens == "cells-agreement" and r.predictor == "geography null"),
     "geography null features changed (ADR-0033: density + slope + elevation + MMI; the archived rq3f oracle used coast distance)"),
]


def main(paths):
    ora = pd.read_csv(ORACLE)
    new = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    m = new.merge(ora, on=KEY, how="left", suffixes=("_new", "_oracle"), indicator=True)
    m["radius"] = m["radius"].astype(object)
    missing = m[m._merge == "left_only"]
    both = m[m._merge == "both"].copy()
    both["diff"] = (both.value_new - both.value_oracle).abs()
    bad = both[both["diff"] > 1e-9]
    explained, unexplained = [], []
    for _, r in bad.iterrows():
        why = next((w for pred, w in EXCEPTIONS if pred(r)), None)
        (explained if why else unexplained).append((r, why))
    # oracle rows the pipeline should have produced but did not (same region/lens present)
    covered = set(zip(new.region, new.lens))
    ora_cov = ora[[ (a, b) in covered for a, b in zip(ora.region, ora.lens)]]
    not_produced = ora_cov.merge(new[KEY], on=KEY, how="left", indicator=True).query("_merge == 'left_only'")
    not_produced = not_produced[~not_produced.apply(lambda r: any(pred(pd.Series({**r, "source_oracle": r.source, "value_new": np.nan, "value_oracle": r.value})) for pred, _ in EXCEPTIONS), axis=1)] if len(not_produced) else not_produced
    print(f"pipeline rows: {len(new)} | matched oracle rows: {len(both)} | identical: {len(both) - len(bad)}")
    print(f"explained differences: {len(explained)} | UNEXPLAINED differences: {len(unexplained)} | pipeline rows absent from oracle: {len(missing)} | oracle rows not produced: {len(not_produced)}")
    for r, why in explained[:6]:
        print(f"  ok  {r.region}/{r.lens}/{r.radius}/{r.predictor}/{r.metric}: {r.value_oracle} -> {r.value_new}  ({why[:70]})")
    for r, _ in unexplained:   # every row: a capped list once hid 155 of 195
        print(f"  XX  {r.region}/{r.lens}/{r.radius}/{r.predictor}/{r.metric}: oracle {r.value_oracle} vs new {r.value_new}")
    for _, r in missing.head(20).iterrows():
        print(f"  new-only  {r.region}/{r.lens}/{r.radius}/{r.predictor}/{r.metric} = {r.value_new}")
    for _, r in not_produced.head(20).iterrows():
        print(f"  not-produced  {r.region}/{r.lens}/{r.radius}/{r.predictor}/{r.metric} = {r.value}")
    sys.exit(1 if (len(unexplained) or len(not_produced)) else 0)


if __name__ == "__main__":
    main(sys.argv[1:] or [os.path.join(HERE, "results_scorecards.csv")])
