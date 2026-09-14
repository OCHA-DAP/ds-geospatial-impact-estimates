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


def rq2q():
    """Core, r = 10, reference widened to 'possibly damaged' (lens points+possibly). The
    dmg+destroyed rows duplicate rq5b's and are checked equal, then dropped."""
    rel = "RQ2-cems-footprint-points/rq2q_incl_possibly.csv"
    d = load(rel)
    ref = load("RQ5-ensemble/rq5b_six_member.csv").set_index("rule")
    out = []
    for _, x in d.iterrows():
        if x.threshold == "dmg+destroyed":
            r = ref.loc[x.rule]
            if (round(r.P_cems, 3), round(r.R_cems, 3)) != (round(x.P, 3), round(x.R, 3)):
                raise SystemExit(f"rq2q floor differs from rq5b for {x.rule}: {x.P}/{x.R} vs {r.P_cems}/{r.R_cems}")
            continue
        out += rows("core", "points+possibly", 10, x.rule, rel, P=x.P, R=x.R, F1=x.F1, n_flags=x["flags"], n_ref=x.cems_pts)
    return out


def rq2r():
    rel = "RQ2-cems-footprint-points/rq2r_precision_bounds.csv"
    return sum((rows("core", "bounds", 10, x["product"], rel, P_floor=x.P_floor, P_grade=x.P_grade, P_crowd=x.P_crowd, P_upper=x.P_upper,
                     crowd_cov=x.crowd_cov_of_fps, crowd_fp_near_class1=x.crowd_fp_near_class1) for _, x in load(rel).iterrows()), [])


def rq2_chatmap():
    rel = "RQ2-cems-footprint-points/rq2_chatmap_recall.csv"
    out = []
    for _, x in load(rel).iterrows():
        for r, col in ((10, "recall_r10"), (20, "recall_r20"), (50, "recall_r50")):
            out += rows("field", "field", r, x.reference, rel, R=x[col])
        out += rows("field", "field", 20, x.reference, rel, n_field=x.n_field_in_aoi, R_complete=x.complete_r20, n_complete=x.n_complete,
                    R_significant=x.significant_r20, n_significant=x.n_significant, R_minimal=x.minimal_r20, n_minimal=x.n_minimal)
    return out


def rq2k():
    rel = "RQ2-cems-footprint-points/rq2k_field_union_precision.csv"
    out = []
    for _, x in load(rel).iterrows():
        out += rows("core", "field-union", 10, x["product"], rel, P_cems=x.P_cems, P_union=x.P_union, R_cems=x.R_cems, R_union=x.R_union,
                    P_rel_gain=float(str(x.P_rel_gain).rstrip("%")), R_rel_change=float(str(x.R_rel_change).rstrip("%")))
    return out


def rq2s():
    rel = "RQ2-cems-footprint-points/rq2s_flag_totals.csv"
    return sum((rows("all", "flags", None, x["product"], rel, total_flags=x.total_flags, in_cems_extent=x.in_cems_extent, share_outside=x.share_outside)
                for _, x in load(rel).iterrows()), [])


def rq2l():
    rel = "RQ2-cems-footprint-points/rq2l_cems_grade_recall.csv"
    return sum((rows("core", "grade-recall", 10, x["product"], rel, P_vs_damaged=x.P_vs_damaged, P_vs_destroyed=x.P_vs_destroyed,
                     R_of_damaged=x.R_of_damaged, R_of_destroyed=x.R_of_destroyed) for _, x in load(rel).iterrows()), [])


def rq2o():
    rel = "RQ2-cems-footprint-points/rq2o_uh_west_strip.csv"
    return sum((rows(f"strip-{x.side}", "points", 10, x["product"], rel, P=x.P_cems, n_flags=x.n_flags, flag_share=x.flag_share, n_bld=x.n_bld, n_cems=x.n_cems)
                for _, x in load(rel).iterrows()), [])


def rq2h():
    rel = "RQ2-cems-footprint-points/rq2h_osu_v0_v1.csv"
    return sum((rows("osu-versions", "points", 10, x.version, rel, P=x.P, R=x.R, F1=x.F1, n_flags=x["flags"], n_ref=x.cems_pts, R_field20=x.R_field)
                for _, x in load(rel).iterrows()), [])


def rq2p():
    rel = "RQ2-cems-footprint-points/rq2p_osu_v1_tiers.csv"
    return sum((rows(f"osu-tiers:{x.region}", "points", 10, x.cut, rel, P=x.P, R=x.R, F1=x.F1, n_flags=x["flags"])
                for _, x in load(rel).iterrows()), [])


def rq2_density_null():
    rel = "RQ2-cems-footprint-points/rq2_density_null.csv"
    return sum((rows(x.area, "density", None, x["product"], rel, n_bldg=x.n_bldg, n_cems=x.n_cems, n_flag=x.n_flag, flag_pct=x.flag_pct,
                     R=x.recall, enrichment=x.enrichment, P=x.precision, rand_prec=x.rand_prec, lift=x.lift) for _, x in load(rel).iterrows()), [])


def rq2_ms_confidence():
    rel = "RQ2-cems-footprint-points/rq2_ms_confidence_curve.csv"
    return sum((rows("ms-aoi", "confidence", 10, f"thresh={x.thresh:.2f}", rel, n_flags=x.n_flag, P=x.precision, R=x.recall, F1=x.f1)
                for _, x in load(rel).iterrows()), [])


def rq3f():
    out = []
    for region, rel in (("asd", "RQ3-prioritization-error-structure/rq3f_null_ranking.csv"),
                        ("core", "RQ3-prioritization-error-structure/rq3f_null_ranking_core.csv"),
                        ("Caraballeda", "RQ3-prioritization-error-structure/rq3f_null_ranking_caraballeda.csv")):
        for _, x in load(rel).iterrows():
            out += rows(region, "cells", int(x.res), x["product"], rel, rho=x.rho_product, rho_null=x.rho_null, delta=x.delta,
                        top20=x.top20_product, top20_null=x.top20_null, cells=x.cells)
    return out


def rq3h():
    rel = "RQ3-prioritization-error-structure/rq3h_agreement_ranking.csv"
    return sum((rows("core", "cells-agreement", int(x.res), x.predictor, rel, rho=x.rho, top20=x.top20, top20_exp=x.top20_exp, rho_frac=x.rho_frac, cells=x.cells, cells_frac=x.cells_frac)
                for _, x in load(rel).iterrows()), [])


def rq3g():
    rel = "RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv"
    return sum((rows("asd", "cells-fraction", int(x.res), x["product"], rel, rho_count=x.rho_count, rho_null_count=x.rho_null_count,
                     rho_frac=x.rho_frac, rho_null_frac=x.rho_null_frac, cells_count=x.cells_count, cells_frac=x.cells_frac) for _, x in load(rel).iterrows()), [])


def rq3b():
    rel = "RQ3-prioritization-error-structure/rq3b_per_area_moran.csv"
    return sum((rows(x.area, "moran", 8, x["product"], rel, moran_I=x.moran_I, p=x.p, flag_pct=x.flag_pct, cells=x.cells, n_cems=x.n_cems)
                for _, x in load(rel).iterrows()), [])


def rq3d():
    rel = "RQ3-prioritization-error-structure/rq3d_lisa_summary.csv"
    return sum((rows("asd", "lisa", 8, x["product"], rel, cells=x.cells, HH=x.HH, LL=x.LL, HL=x.HL, LH=x.LH, ns=x.ns) for _, x in load(rel).iterrows()), [])


def rq8():
    out = []
    for r in (10, 20, 30):
        rel = f"RQ8-learned-fusion/rq8_best_f1_r{r}.csv"
        for _, x in load(rel).iterrows():
            out += rows("core", "labels", r, x.predictor, rel, P=x.precision, R=x.recall, F1=x.f1, n_flags=x.n_flags, threshold=x.threshold)
    return out


def rq8b():
    out = []
    for r in (10, 20):
        rel = f"RQ8-learned-fusion/rq8b_asdelivered_baseline_r{r}.csv"
        for _, x in load(rel).iterrows():
            out += rows("asd", "labels", r, x["product"], rel, n_bld=x.n_bld, n_pos=x.n_pos, n_flags=x.n_flags, AP=x.AP_product, AP_dayzero=x.AP_dayzero,
                        P=x.P_product, R=x.R_product, P_dayzero=x.P_dayzero_matched, R_dayzero=x.R_dayzero_matched)
    return out


def rq9():
    out = []
    rel = "RQ9-uncertainty/rq9_ci_core.csv"
    for _, x in load(rel).iterrows():
        out += rows("core", "ci", int(x.radius), x.rule, rel, **{f"{x.metric}": x.point, f"{x.metric}_lo": x.lo, f"{x.metric}_hi": x.hi})
    rel = "RQ9-uncertainty/rq9_ci_asdelivered_r10.csv"
    for _, x in load(rel).iterrows():
        out += rows("asd", "ci", int(x.radius), x.rule, rel, **{f"{x.metric}": x.point, f"{x.metric}_lo": x.lo, f"{x.metric}_hi": x.hi})
    rel = "RQ9-uncertainty/rq9_ci_models_r10.csv"
    for _, x in load(rel).iterrows():
        out += rows("core", "ci-labels", 10, x.predictor, rel, **{f"{x.metric}": x.point, f"{x.metric}_lo": x.lo, f"{x.metric}_hi": x.hi})
    return out


def rq7():
    out = []
    rel = "RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv"
    for _, x in load(rel).iterrows():
        out += rows("asd", "crowd-round2", 10, x["product"], rel, P_crowd_r1=x.P_crowd_r1, P_crowd_r2swap=x.P_crowd_r2swap, delta=x.delta,
                    strip_share=x.strip_share_of_covered_fps, strip_unmatched=x.strip_unmatched_flags, conf_r1=x.unmatched_conf_share_r1, conf_r2=x.unmatched_conf_share_r2)
    rel = "RQ7-mapswipe-validation/rq7_round2_replication.csv"
    d = load(rel).set_index("metric").value
    out += rows("strip", "crowd-round2", None, "MS", rel, **{k: d[k] for k in d.index})
    return out


def frame():
    rel = "RQ0-matching-basis/native_rerun/shared_base_polygon_core.csv"
    return sum((rows("core", "frame", int(x.radius_m), x.rule, rel, poly_P=x.poly_P, poly_R=x.poly_R, poly_F1=x.poly_F1,
                     centroid_P=x.centroid_P, centroid_R=x.centroid_R, centroid_F1=x.centroid_F1) for _, x in load(rel).iterrows()), [])


SOURCES = [rq5b, rq2i, rq2q, rq2r, rq2_chatmap, rq2k, rq2s, rq2l, rq2o, rq2h, rq2p, rq2_density_null, rq2_ms_confidence,
           rq3f, rq3h, rq3g, rq3b, rq3d, rq8, rq8b, rq9, rq7, frame]


def main():
    out = []
    for fn in SOURCES:
        out += fn()
    res = pd.DataFrame(out)
    bad = res[pd.to_numeric(res.value, errors="coerce").isna()]
    if len(bad):
        raise SystemExit("consolidate: non-numeric values\n" + bad.head(20).to_string())
    res["value"] = res.value.astype(float)
    key = ["region", "lens", "radius", "predictor", "metric"]
    dup = res[res.duplicated(key, keep=False)]
    if len(dup):
        raise SystemExit("consolidate: duplicate keys\n" + dup.sort_values(key).to_string())
    res = res.sort_values(key).reset_index(drop=True)
    res.to_csv(os.path.join(HERE, "results.csv"), index=False)
    print(f"results.csv: {len(res):,} rows from {len(SOURCES)} sources")


if __name__ == "__main__":
    main()
