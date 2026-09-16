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
PAPER = os.path.join(HERE, "..")
FROZEN = os.path.join(PAPER, "frozen")            # signed-off copies of the heavy/diagnostic outputs (MANIFEST.csv)
ORACLE_ROOT = os.path.join(PAPER, "artefacts")   # the archive: only the --oracle build reads it
PRODUCTS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
RULES = [f"{k}-of-6" for k in range(1, 7)]
# The six pairs the ARCHIVED rq5b script computed (2026-07-15 benchmark set). Only the --oracle
# adapter below reads them; the pipeline's own 15-pair set is defined in paperlib.PAIRS and reaches
# results.csv through pipeline/results_scorecards.csv, not through this list. (No paperlib import
# here: diff_results.py copies this file alone into a temp dir and runs it there.)
PAIRS = ["IMPACT∧OSU", "MS∧UH", "MS∧LIST", "LIST∧UH", "UNEP∧OSU", "MS∧UNEP"]


LOADED: set = set()   # every CSV read, for diff_results.py


ORACLE_MODE = False


def load(rel: str) -> pd.DataFrame:
    """SOURCES read the signed-off copy in frozen/ (by file name); the --oracle build reads the archive."""
    LOADED.add(rel)
    p = os.path.join(ORACLE_ROOT, rel) if ORACLE_MODE else os.path.join(FROZEN, os.path.basename(rel))
    if not os.path.exists(p):
        raise FileNotFoundError(f"consolidate: missing {p}")
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
            out += rows("core", "points", r, pred, rel, P=x.get("P_cems"), R=x.get("R_cems"), F1=x.get("F1_cems"), n_flags=x.get("flagged"), R_field20=x.get("R_field_r20"))
            if r == 10:
                out += rows("core", "crowd", 10, pred, rel, P_crowd=x.get("P_crowd"), crowd_cov=x.get("crowd_cov_of_fps"), fp_crowd_damaged=x.get("FP_crowd_damaged"))
    return out


def rq2i():
    """As-delivered and per-AOI scorecard, points lens, r = 10."""
    rel = "RQ2-cems-footprint-points/rq2i_per_aoi_scorecard.csv"
    d = load(rel)
    out = []
    for _, x in d.drop_duplicates(["aoi", "product"]).iterrows():
        region = "asd" if x["aoi"] == "ALL (as delivered)" else x.get("aoi")
        out += rows(region, "points", 10, x["product"], rel, P=x.get("P_cems"), R=x.get("R_cems"), n_flags=x.get("n_flags"), n_bld=x.get("n_bld"), flag_share=x.get("flag_share"), n_cems=x.get("n_cems"))
        out += rows(region, "crowd", 10, x["product"], rel, P_crowd=x.get("P_crowd"), crowd_cov=x.get("crowd_cov_of_fps"), fp_crowd_damaged=x.get("fp_crowd_damaged"))
    return out


def rq2q():
    """Core, r = 10, reference widened to 'possibly damaged' (lens points+possibly). The
    dmg+destroyed rows duplicate rq5b's and are checked equal, then dropped."""
    rel = "RQ2-cems-footprint-points/rq2q_incl_possibly.csv"
    d = load(rel)
    ref = load("RQ5-ensemble/rq5b_six_member.csv").set_index("rule")
    out = []
    for _, x in d.iterrows():
        if x["threshold"] == "dmg+destroyed":
            r = ref.loc[x["rule"]]
            if (round(r.P_cems, 3), round(r.R_cems, 3)) != (round(x["P"], 3), round(x["R"], 3)):
                raise SystemExit(f"rq2q floor differs from rq5b for {x["rule"]}: {x.get("P")}/{x.get("R")} vs {r.P_cems}/{r.R_cems}")
            continue
        out += rows("core", "points+possibly", 10, x["rule"], rel, P=x.get("P"), R=x.get("R"), F1=x.get("F1"), n_flags=x["flags"], n_ref=x.get("cems_pts"))
    return out


def rq2r():
    rel = "RQ2-cems-footprint-points/rq2r_precision_bounds.csv"
    return sum((rows("core", "bounds", 10, x["product"], rel, P_floor=x.get("P_floor"), P_grade=x.get("P_grade"), P_crowd=x.get("P_crowd"), P_upper=x.get("P_upper"),
                     crowd_cov=x.get("crowd_cov_of_fps"), crowd_fp_near_class1=x.get("crowd_fp_near_class1")) for _, x in load(rel).iterrows()), [])


def rq2_chatmap():
    rel = "RQ2-cems-footprint-points/rq2_chatmap_recall.csv"
    out = []
    for _, x in load(rel).iterrows():
        for r, col in ((10, "recall_r10"), (20, "recall_r20"), (50, "recall_r50")):
            out += rows("field", "field", r, x["reference"], rel, R=x[col])
        out += rows("field", "field", 20, x["reference"], rel, n_field=x.get("n_field_in_aoi"), R_complete=x.get("complete_r20"), n_complete=x.get("n_complete"),
                    R_significant=x.get("significant_r20"), n_significant=x.get("n_significant"), R_minimal=x.get("minimal_r20"), n_minimal=x.get("n_minimal"))
    return out


def rq2k():
    rel = "RQ2-cems-footprint-points/rq2k_field_union_precision.csv"
    out = []
    for _, x in load(rel).iterrows():
        out += rows("core", "field-union", 10, x["product"], rel, P_cems=x.get("P_cems"), P_union=x.get("P_union"), R_cems=x.get("R_cems"), R_union=x.get("R_union"),
                    P_rel_gain=float(str(x.get("P_rel_gain")).rstrip("%")), R_rel_change=float(str(x.get("R_rel_change")).rstrip("%")))
    return out


def rq2s():
    rel = "RQ2-cems-footprint-points/rq2s_flag_totals.csv"
    return sum((rows("all", "flags", None, x["product"], rel, total_flags=x.get("total_flags"), in_cems_extent=x.get("in_cems_extent"), share_outside=x.get("share_outside"))
                for _, x in load(rel).iterrows()), [])


def rq2l():
    rel = "RQ2-cems-footprint-points/rq2l_cems_grade_recall.csv"
    return sum((rows("core", "grade-recall", 10, x["product"], rel, P_vs_damaged=x.get("P_vs_damaged"), P_vs_destroyed=x.get("P_vs_destroyed"),
                     R_of_damaged=x.get("R_of_damaged"), R_of_destroyed=x.get("R_of_destroyed")) for _, x in load(rel).iterrows()), [])


def rq2o():
    rel = "RQ2-cems-footprint-points/rq2o_uh_west_strip.csv"
    return sum((rows(f"strip-{x["side"]}", "points", 10, x["product"], rel, P=x.get("P_cems"), n_flags=x.get("n_flags"), flag_share=x.get("flag_share"), n_bld=x.get("n_bld"), n_cems=x.get("n_cems"))
                for _, x in load(rel).iterrows()), [])


def rq2h():
    rel = "RQ2-cems-footprint-points/rq2h_osu_v0_v1.csv"
    return sum((rows("osu-versions", "points", 10, x["version"], rel, P=x.get("P"), R=x.get("R"), F1=x.get("F1"), n_flags=x["flags"], n_ref=x.get("cems_pts"), R_field20=x.get("R_field"))
                for _, x in load(rel).iterrows()), [])


def rq2p():
    rel = "RQ2-cems-footprint-points/rq2p_osu_v1_tiers.csv"
    return sum((rows(f"osu-tiers:{x["region"]}", "points", 10, x["cut"], rel, P=x.get("P"), R=x.get("R"), F1=x.get("F1"), n_flags=x["flags"])
                for _, x in load(rel).iterrows()), [])


def rq2_density_null():
    rel = "RQ2-cems-footprint-points/rq2_density_null.csv"
    return sum((rows(x["area"], "density", None, x["product"], rel, n_bldg=x.get("n_bldg"), n_cems=x.get("n_cems"), n_flag=x.get("n_flag"), flag_pct=x.get("flag_pct"),
                     R=x.get("recall"), enrichment=x.get("enrichment"), P=x.get("precision"), rand_prec=x.get("rand_prec"), lift=x.get("lift")) for _, x in load(rel).iterrows()), [])


def rq2_ms_confidence():
    rel = "RQ2-cems-footprint-points/rq2_ms_confidence_curve.csv"
    return sum((rows("ms-aoi", "confidence", 10, f"thresh={x["thresh"]:.2f}", rel, n_flags=x.get("n_flag"), P=x.get("precision"), R=x.get("recall"), F1=x.get("f1"))
                for _, x in load(rel).iterrows()), [])


def rq3f():
    out = []
    for region, rel in (("asd", "RQ3-prioritization-error-structure/rq3f_null_ranking.csv"),
                        ("core", "RQ3-prioritization-error-structure/rq3f_null_ranking_core.csv"),
                        ("Caraballeda", "RQ3-prioritization-error-structure/rq3f_null_ranking_caraballeda.csv")):
        for _, x in load(rel).iterrows():
            out += rows(region, "cells", int(x["res"]), x["product"], rel, rho=x.get("rho_product"), rho_null=x.get("rho_null"), delta=x.get("delta"),
                        top20=x.get("top20_product"), top20_null=x.get("top20_null"), cells=x.get("cells"))
    return out


def rq3h():
    rel = "RQ3-prioritization-error-structure/rq3h_agreement_ranking.csv"
    return sum((rows("core", "cells-agreement", int(x["res"]), x["predictor"], rel, rho=x.get("rho"), top20=x.get("top20"), top20_exp=x.get("top20_exp"), rho_frac=x.get("rho_frac"), cells=x.get("cells"), cells_frac=x.get("cells_frac"))
                for _, x in load(rel).iterrows()), [])


def rq3g():
    rel = "RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv"
    return sum((rows("asd", "cells-fraction", int(x["res"]), x["product"], rel, rho_count=x.get("rho_count"), rho_null_count=x.get("rho_null_count"),
                     rho_frac=x.get("rho_frac"), rho_null_frac=x.get("rho_null_frac"), cells_count=x.get("cells_count"), cells_frac=x.get("cells_frac")) for _, x in load(rel).iterrows()), [])


def rq3b():
    rel = "RQ3-prioritization-error-structure/rq3b_per_area_moran.csv"
    return sum((rows(x["area"], "moran", 8, x["product"], rel, moran_I=x.get("moran_I"), p=x.get("p"), flag_pct=x.get("flag_pct"), cells=x.get("cells"), n_cems=x.get("n_cems"))
                for _, x in load(rel).iterrows()), [])


def rq3d():
    rel = "RQ3-prioritization-error-structure/rq3d_lisa_summary.csv"
    return sum((rows("asd", "lisa", 8, x["product"], rel, cells=x.get("cells"), HH=x.get("HH"), LL=x.get("LL"), HL=x.get("HL"), LH=x.get("LH"), ns=x.get("ns")) for _, x in load(rel).iterrows()), [])


def rq8():
    out = []
    for r in (10, 20, 30):
        rel = f"RQ8-learned-fusion/rq8_best_f1_r{r}.csv"
        for _, x in load(rel).iterrows():
            out += rows("core", "labels", r, x["predictor"], rel, P=x.get("precision"), R=x.get("recall"), F1=x.get("f1"), n_flags=x.get("n_flags"), threshold=x.get("threshold"))
    return out


def rq8b():
    out = []
    for r in (10, 20):
        rel = f"RQ8-learned-fusion/rq8b_asdelivered_baseline_r{r}.csv"
        for _, x in load(rel).iterrows():
            out += rows("asd", "labels", r, x["product"], rel, n_bld=x.get("n_bld"), n_pos=x.get("n_pos"), n_flags=x.get("n_flags"), AP=x.get("AP_product"), AP_dayzero=x.get("AP_dayzero"),
                        P=x.get("P_product"), R=x.get("R_product"), P_dayzero=x.get("P_dayzero_matched"), R_dayzero=x.get("R_dayzero_matched"))
    return out


def rq8c():
    """Fusion appendix: the frozen operating points re-scored under three reference grades (labels lens)."""
    rel = "RQ8-learned-fusion/rq8c_basis_pr_r10.csv"
    return sum((rows("core", f"labels-{x['basis']}", 10, x["predictor"], rel, P=x.get("precision"), R=x.get("recall"), F1=x.get("f1"),
                     n_flags=x.get("n_flags"), n_pos=x.get("n_pos")) for _, x in load(rel).iterrows()), [])


def rq8d():
    """Null appendix: covariate ablation of the geography null (labels lens, core, 10 m). Predictor = feature set."""
    rel = "RQ8-learned-fusion/rq8d_null_ablation.csv"
    return sum((rows("core", "labels-ablation", 10, x["features"], rel, AP=x.get("AP"), F1=x.get("best_F1"), P=x.get("P"), R=x.get("R"),
                     rho_res8=x.get("rho_res8"), rho_res9=x.get("rho_res9")) for _, x in load(rel).iterrows()), [])


def rq9():
    out = []
    rel = "RQ9-uncertainty/rq9_ci_core.csv"
    for _, x in load(rel).iterrows():
        out += rows("core", "ci", int(x["radius"]), x["rule"], rel, **{f"{x["metric"]}": x.get("point"), f"{x["metric"]}_lo": x.get("lo"), f"{x["metric"]}_hi": x.get("hi")})
    rel = "RQ9-uncertainty/rq9_ci_asdelivered_r10.csv"
    for _, x in load(rel).iterrows():
        out += rows("asd", "ci", int(x["radius"]), x["rule"], rel, **{f"{x["metric"]}": x.get("point"), f"{x["metric"]}_lo": x.get("lo"), f"{x["metric"]}_hi": x.get("hi")})
    rel = "RQ9-uncertainty/rq9_ci_models_r10.csv"
    for _, x in load(rel).iterrows():
        out += rows("core", "ci-labels", 10, x["predictor"], rel, **{f"{x["metric"]}": x.get("point"), f"{x["metric"]}_lo": x.get("lo"), f"{x["metric"]}_hi": x.get("hi")})
    return out


def rq7():
    out = []
    rel = "RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv"
    for _, x in load(rel).iterrows():
        out += rows("asd", "crowd-round2", 10, x["product"], rel, P_crowd_r1=x.get("P_crowd_r1"), P_crowd_r2swap=x.get("P_crowd_r2swap"), delta=x.get("delta"),
                    strip_share=x.get("strip_share_of_covered_fps"), strip_unmatched=x.get("strip_unmatched_flags"), conf_r1=x.get("unmatched_conf_share_r1"), conf_r2=x.get("unmatched_conf_share_r2"))
    rel = "RQ7-mapswipe-validation/rq7_round2_replication.csv"
    d = load(rel).set_index("metric").value
    out += rows("strip", "crowd-round2", None, "MS", rel, **{k: d[k] for k in d.index})
    return out


def frame():
    rel = "RQ0-matching-basis/native_rerun/shared_base_polygon_core.csv"
    return sum((rows("core", "frame", int(x["radius_m"]), x["rule"], rel, poly_P=x.get("poly_P"), poly_R=x.get("poly_R"), poly_F1=x.get("poly_F1"),
                     centroid_P=x.get("centroid_P"), centroid_R=x.get("centroid_R"), centroid_F1=x.get("centroid_F1"),
                     flags_intersects=x.get("flags"), flags_centroid=x.get("centroid_flags")) for _, x in load(rel).iterrows()), [])


PIPELINE = HERE


def pipeline_rows(name):
    """Rows written by a compact pipeline module (pipeline/results_<name>.csv)."""
    def fn():
        p = os.path.join(PIPELINE, f"results_{name}.csv")
        if not os.path.exists(p):
            raise FileNotFoundError(f"consolidate: pipeline output missing: pipeline/results_{name}.csv (run `snakemake {name}`)")
        LOADED.add(f"../pipeline/results_{name}.csv")
        return pd.read_csv(p).to_dict("records")
    fn.__name__ = f"pipeline_{name}"
    return fn


# Current sources: the compact modules (ADR-0032) plus adapters over the frozen heavy chain and
# the appendix-only diagnostics that were not migrated (their scripts remain under artefacts/).
SOURCES = [pipeline_rows("scorecards"), pipeline_rows("ranking"), pipeline_rows("facts"),
           rq2h, rq2p, rq2_density_null, rq2_ms_confidence, rq3g, rq3b, rq3d, rq8, rq8b, rq8c, rq8d, rq9, rq7, frame]

# The oracle: every number from the frozen per-RQ scripts, as consolidated on 2026-09-14
# (artefacts/results_oracle_frozen.csv). `python consolidate.py --oracle` rebuilds it.
ORACLE_SOURCES = [rq5b, rq2i, rq2q, rq2r, rq2_chatmap, rq2k, rq2s, rq2l, rq2o, rq2h, rq2p, rq2_density_null, rq2_ms_confidence,
                  rq3f, rq3h, rq3g, rq3b, rq3d, rq8, rq8b, rq9, rq7, frame]


def main():
    import sys
    oracle = "--oracle" in sys.argv[1:]
    global ORACLE_MODE
    ORACLE_MODE = oracle
    sources = ORACLE_SOURCES if oracle else SOURCES
    out = []
    for fn in sources:
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
    name = "results_oracle_frozen.csv" if oracle else "results.csv"
    res.to_csv(os.path.join(PAPER, name), index=False)
    print(f"{name}: {len(res):,} rows from {len(sources)} sources")


if __name__ == "__main__":
    main()
