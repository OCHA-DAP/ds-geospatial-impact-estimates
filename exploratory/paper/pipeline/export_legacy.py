"""Write the per-RQ CSVs that the figure scripts and two frozen anchors (rq3g, rq9) still read,
in their original column layouts, FROM the pipeline's results rows. One computation, two
layouts: nothing here is recomputed, only reshaped.

Produces (under pipeline/legacy/): rq2_chatmap_recall.csv, rq2r_precision_bounds.csv,
rq5b_six_member{,_r20,_r30}.csv, rq2i_per_aoi_scorecard.csv, rq3f_null_ranking{,_core,_caraballeda}.csv,
rq3h_agreement_ranking.csv.

Usage: python export_legacy.py   (run from exploratory/paper; used by the Snakefile's legacy_csvs rule)
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "legacy")   # legacy-layout CSVs live here, flat
PRODUCTS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
RULES = [f"{k}-of-6" for k in range(1, 7)]


def pair_names(sc: pd.DataFrame) -> list:
    """The two-product rules present in the scorecard rows (paperlib.PAIRS, all 15), in first-seen order."""
    seen = [p for p in sc.predictor if "∧" in str(p)]
    return list(dict.fromkeys(seen))


def wide(df, region, lens, radius):
    m = (df.region == region) & (df.lens == lens)
    m &= df.radius.isna() if radius is None else (df.radius == radius)
    sub = df[m]
    if not len(sub):
        raise SystemExit(f"export_legacy: no rows for {region}/{lens}/{radius}")
    return sub.pivot_table(index="predictor", columns="metric", values="value", aggfunc="first")


def write(df: pd.DataFrame, rel: str):
    path = os.path.join(A, os.path.basename(rel))
    os.makedirs(A, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  {rel}: {len(df)} rows")


def main():
    sc = pd.read_csv(os.path.join(HERE, "results_scorecards.csv"))
    rk = pd.read_csv(os.path.join(HERE, "results_ranking.csv"))

    # rq5b_six_member{,_r20,_r30}.csv — rule, flagged, P_cems, R_cems, F1_cems, R_field_r20, FP_crowd_damaged, crowd_cov_of_fps, P_crowd
    order = PRODUCTS + pair_names(sc) + RULES
    for r, name in ((10, "rq5b_six_member.csv"), (20, "rq5b_six_member_r20.csv"), (30, "rq5b_six_member_r30.csv")):
        p = wide(sc, "core", "points", r).loc[order]
        out = pd.DataFrame({"rule": order, "flagged": p.n_flags.astype(int).values, "P_cems": p.P.values, "R_cems": p.R.values,
                            "F1_cems": p.F1.values, "R_field_r20": p.R_field20.values})
        if r == 10:
            c = wide(sc, "core", "crowd", 10).loc[order]
            out["FP_crowd_damaged"] = c.fp_crowd_damaged.values; out["crowd_cov_of_fps"] = c.crowd_cov.values; out["P_crowd"] = c.P_crowd.values
        write(out, os.path.join("RQ5-ensemble", name))

    # rq2i_per_aoi_scorecard.csv — aoi, product, n_bld, n_flags, flag_share, n_cems, P_cems, R_cems, crowd_cov_of_fps, fp_crowd_damaged, P_crowd
    aois = ["asd", "Caraballeda", "Caracas", "Moron", "San Felipe", "Santa Cruz"]
    rows = []
    for aoi in aois:
        pts = wide(sc, aoi, "points", 10)
        cr = wide(sc, aoi, "crowd", 10) if ((sc.region == aoi) & (sc.lens == "crowd")).any() else None
        for p in PRODUCTS:
            if p not in pts.index:
                continue
            x = pts.loc[p]
            row = dict(aoi="ALL (as delivered)" if aoi == "asd" else aoi, product=p, n_bld=int(x.n_bld), n_flags=int(x.n_flags),
                       flag_share=x.flag_share, n_cems=int(x.n_cems), P_cems=x.get("P", np.nan), R_cems=x.get("R", np.nan))
            if cr is not None and p in cr.index:
                y = cr.loc[p]
                row.update(crowd_cov_of_fps=y.get("crowd_cov", np.nan), fp_crowd_damaged=y.get("fp_crowd_damaged", np.nan), P_crowd=y.get("P_crowd", np.nan))
            rows.append(row)
    write(pd.DataFrame(rows), os.path.join("RQ2-cems-footprint-points", "rq2i_per_aoi_scorecard.csv"))

    # rq2r_precision_bounds.csv — product, n_flags, P_floor, P_grade, P_crowd, P_upper, crowd_cov_of_fps, crowd_fp_near_class1
    b = wide(sc, "core", "bounds", 10).loc[PRODUCTS]; nfl = wide(sc, "core", "points", 10).loc[PRODUCTS].n_flags
    write(pd.DataFrame({"product": PRODUCTS, "n_flags": nfl.astype(int).values, "P_floor": b.P_floor.values, "P_grade": b.P_grade.values,
                        "P_crowd": b.P_crowd.values, "P_upper": b.P_upper.values, "crowd_cov_of_fps": b.crowd_cov.values,
                        "crowd_fp_near_class1": b.crowd_fp_near_class1.values}), os.path.join("RQ2-cems-footprint-points", "rq2r_precision_bounds.csv"))

    # rq2_chatmap_recall.csv — reference, n_field_in_aoi, recall_r20, recall_r10, recall_r50, complete_r20, n_complete, significant_r20, n_significant, minimal_r20, n_minimal
    f = sc[(sc.region == "field") & (sc.lens == "field")]
    refs = list(dict.fromkeys(f.predictor))
    rows = []
    for ref in refs:
        g = f[f.predictor == ref]
        def v(metric, radius):
            q = g[(g.metric == metric) & (g.radius == radius)].value
            return float(q.iloc[0]) if len(q) else np.nan
        rows.append(dict(reference=ref, n_field_in_aoi=v("n_field", 20), recall_r20=v("R", 20), recall_r10=v("R", 10), recall_r50=v("R", 50),
                         complete_r20=v("R_complete", 20), n_complete=v("n_complete", 20), significant_r20=v("R_significant", 20),
                         n_significant=v("n_significant", 20), minimal_r20=v("R_minimal", 20), n_minimal=v("n_minimal", 20)))
    out = pd.DataFrame(rows); out["n_field_in_aoi"] = out.n_field_in_aoi.astype("Int64")
    write(out, os.path.join("RQ2-cems-footprint-points", "rq2_chatmap_recall.csv"))

    # rq3f_null_ranking{,_core,_caraballeda}.csv — res, product, cells, rho_product, rho_null, delta, top20_product, top20_null
    for region, name in (("asd", "rq3f_null_ranking.csv"), ("core", "rq3f_null_ranking_core.csv"), ("Caraballeda", "rq3f_null_ranking_caraballeda.csv")):
        c = rk[(rk.region == region) & (rk.lens == "cells")]
        w = c.pivot_table(index=["radius", "predictor"], columns="metric", values="value", aggfunc="first").reset_index()
        out = pd.DataFrame({"res": w.radius.astype(int), "product": w.predictor, "cells": w.cells.astype(int), "rho_product": w.rho, "rho_null": w.rho_null,
                            "delta": w.delta, "top20_product": w.top20, "top20_null": w.top20_null})
        prod_order = {"Microsoft": 0, "IMPACT v2": 1, "OSU": 2, "UH": 3, "LIST": 4, "UNEP": 5}
        out = out.assign(_o=out["product"].map(prod_order)).sort_values(["_o", "res"], ascending=[True, False]).drop(columns="_o")
        write(out, os.path.join("RQ3-prioritization-error-structure", name))

    # rq3h_agreement_ranking.csv — res, predictor, cells, rho, top20, top20_exp, rho_frac, cells_frac
    h = rk[(rk.region == "core") & (rk.lens == "cells-agreement")]
    w = h.pivot_table(index=["radius", "predictor"], columns="metric", values="value", aggfunc="first").reset_index()
    out = pd.DataFrame({"res": w.radius.astype(int), "predictor": w.predictor, "cells": w.cells.astype(int), "rho": w.rho, "top20": w.top20,
                        "top20_exp": w.top20_exp, "rho_frac": w.rho_frac, "cells_frac": w.cells_frac.astype(int)}).sort_values(["res"], ascending=False, kind="stable")
    write(out, os.path.join("RQ3-prioritization-error-structure", "rq3h_agreement_ranking.csv"))
    print("legacy CSVs exported from pipeline results")


if __name__ == "__main__":
    main()
