"""Consolidate every per-script CSV the brief uses into ONE long results table.

results.csv columns
    region     core | asd (as delivered) | <AOI name> | strip-west | strip-east | ...
    lens       points  (P/R against CEMS reference points: the scorecard lens)
               labels  (against buildings labelled by a CEMS point within r: the fusion lens)
               field   (against ChatMap field reports)
               cells   (area ranking on H3 cells)
               crowd   (crowd adjudication quantities)
               flags   (flag counts and shares; no reference involved)
    radius     matching radius in metres (or H3 resolution for cells, or blank)
    predictor  MS | IMPACT | OSU | UH | LIST | UNEP | k-of-6 | pairs | geography null | fusion | ...
    metric     P | R | F1 | n_flags | ... (one row per metric)
    value      float
    source     the CSV the value came from (relative to artefacts/)

Each SOURCE below is a small function mapping one CSV to rows. Adding a number to the brief
means adding a row here, never typing it. Missing files raise; nothing is skipped silently.
"""
from __future__ import annotations

import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
RULES = [f"{k}-of-6" for k in range(1, 7)]
PAIRS = ["IMPACT∧OSU", "MS∧UH", "MS∧LIST", "LIST∧UH", "UNEP∧OSU", "MS∧UNEP"]


def load(rel: str) -> pd.DataFrame:
    p = os.path.join(HERE, rel)
    if not os.path.exists(p):
        raise FileNotFoundError(f"consolidate: missing {rel}")
    return pd.read_csv(p)


def rows(region, lens, radius, predictor, source, **metrics):
    return [dict(region=region, lens=lens, radius=radius, predictor=predictor, metric=m, value=v, source=source)
            for m, v in metrics.items() if pd.notna(v)]


# ---------------------------------------------------------------- sources
def rq5b():
    """Core scorecard, points lens, r = 10/20/30: products, pairs, k-of-6 rules; crowd credit at 10 m."""
    out = []
    for r, rel in ((10, "RQ5-ensemble/rq5b_six_member.csv"), (20, "RQ5-ensemble/rq5b_six_member_r20.csv"), (30, "RQ5-ensemble/rq5b_six_member_r30.csv")):
        d = load(rel).set_index("rule")
        for pred in PRODUCTS + PAIRS + RULES:
            x = d.loc[pred]
            out += rows("core", "points", r, pred, rel, P=x.P_cems, R=x.R_cems, F1=x.F1_cems, n_flags=x.flagged, R_field20=x.R_field_r20)
            if r == 10:
                out += rows("core", "crowd", 10, pred, rel, P_crowd=x.P_crowd, crowd_cov=x.crowd_cov_of_fps, fp_crowd_damaged=x.FP_crowd_damaged)
    return out


def rq2i():
    """As-delivered and per-AOI scorecard, points lens, r = 10."""
    rel = "RQ2-cems-footprint-points/rq2i_per_aoi_scorecard.csv"
    d = load(rel)
    out = []
    for _, x in d.drop_duplicates(["aoi", "product"]).iterrows():
        region = "asd" if x.aoi == "ALL (as delivered)" else x.aoi
        out += rows(region, "points", 10, x["product"], rel, P=x.P_cems, R=x.R_cems, n_flags=x.n_flags, n_bld=x.n_bld, flag_share=x.flag_share, n_cems=x.n_cems)
        out += rows(region, "crowd", 10, x["product"], rel, P_crowd=x.get("P_crowd"), crowd_cov=x.crowd_cov_of_fps, fp_crowd_damaged=x.fp_crowd_damaged)
    return out


SOURCES = [rq5b, rq2i]


def main():
    out = []
    for fn in SOURCES:
        out += fn()
    res = pd.DataFrame(out)
    key = ["region", "lens", "radius", "predictor", "metric"]
    dup = res[res.duplicated(key, keep=False)]
    if len(dup):
        raise SystemExit("consolidate: duplicate keys\n" + dup.sort_values(key).to_string())
    res = res.sort_values(key).reset_index(drop=True)
    res.to_csv(os.path.join(HERE, "results.csv"), index=False)
    print(f"results.csv: {len(res):,} rows from {len(SOURCES)} sources")


if __name__ == "__main__":
    main()
