"""Scorecards: precision/recall of every predictor against the CEMS reference, as rows of the
results table (region, lens, radius, predictor, metric, value, source).

Vertical slice (V2): core region, points lens, r = 10 m, 18 predictors. Extends to the other
radii, the as-delivered and per-AOI regions, the reference-grade bounds and crowd credit.

Usage: python scorecards.py [--slice] -> writes results_scorecards.csv beside this file
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paperlib as pl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = "pipeline/scorecards.py"


def rows(region, lens, radius, predictor, **metrics):
    return [dict(region=region, lens=lens, radius=radius, predictor=predictor, metric=m, value=v, source=SOURCE)
            for m, v in metrics.items() if pd.notna(v)]


def core_points(radii=(10,)) -> list:
    b = pl.buildings()
    core = pl.core_region()
    inb = b[pl.in_region(b, core)]
    ref = pl.reference("floor")
    ref = ref[ref.geometry.within(core)]
    out = []
    preds = pl.predictors(inb)
    for r in radii:
        for name, mask in preds.items():
            s = pl.score(inb[mask], ref, r)
            out += rows("core", "points", r, name, P=round(s["P"], 3), R=round(s["R"], 3), F1=round(s["F1"], 3), n_flags=s["n_flags"])
    return out


def main():
    slice_only = "--slice" in sys.argv[1:]
    out = core_points(radii=(10,) if slice_only else pl.RADII)
    res = pd.DataFrame(out)
    res.to_csv(os.path.join(HERE, "results_scorecards.csv"), index=False)
    print(f"results_scorecards.csv: {len(res)} rows")


if __name__ == "__main__":
    main()
