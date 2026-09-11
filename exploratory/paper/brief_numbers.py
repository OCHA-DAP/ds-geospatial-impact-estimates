"""Single source for every number quoted in manuscript_brief.qmd (ADR-0030).

The brief's prose reads values inline as `{python} N["key"]`; nothing numeric is typed by
hand. Every key below names the artefact CSV it comes from, so a refreeze of the artefact
tree re-points the brief on the next render, and an auditor can trace any figure in the
text to one CSV cell. Missing rows or files raise; there are no fallbacks.

Usage in the .qmd (one setup chunk, `#| include: false`):
    import sys; sys.path.insert(0, ".")
    from brief_numbers import N
"""
from __future__ import annotations

import pathlib

import pandas as pd

A = pathlib.Path(__file__).parent / "artefacts"
PRODUCTS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
LONG = {"MS": "Microsoft", "IMPACT": "IMPACT", "OSU": "OSU", "UH": "UH", "LIST": "LIST", "UNEP": "UNEP"}
N_CEMS_CORE = 1467  # core-region CEMS grade-2/3 points (rq2q cems_pts)


class Numbers(dict):
    def __missing__(self, key):
        raise KeyError(f"brief_numbers: no key {key!r} — define it in brief_numbers.py")


N = Numbers()


# ---------------------------------------------------------------- helpers
def csv(rel: str) -> pd.DataFrame:
    p = A / rel
    if not p.exists():
        raise FileNotFoundError(f"artefact missing: {p}")
    return pd.read_csv(p)


def one(df: pd.DataFrame, **eq) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for k, v in eq.items():
        m &= df[k] == v
    hit = df[m]
    if len(hit) != 1:
        raise ValueError(f"expected one row for {eq}, got {len(hit)}")
    return hit.iloc[0]


def f3(x) -> str:
    return f"{float(x):.3f}"


def f2(x) -> str:
    return f"{float(x):.2f}"


def pct(x, d: int = 0) -> str:
    return f"{100 * float(x):.{d}f}%"


def com(n) -> str:
    return f"{int(round(float(n))):,}"


def rng(a, b, fmt=f3, sep="–") -> str:
    return f"{fmt(min(a, b))}{sep}{fmt(max(a, b))}"


_WORDS = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()


def words(n) -> str:
    n = int(round(float(n)))
    return _WORDS[n] if 0 <= n <= 20 else str(n)


def fa_per_hit(p) -> int:
    """False alarms per true hit at precision p, rounded."""
    return int(round((1 - float(p)) / float(p)))


def signed(x, fmt=f2) -> str:
    return ("+" if float(x) >= 0 else "−") + fmt(abs(float(x)))


def md_table(rows: list[list[str]], header: list[str]) -> str:
    """Pipe table for inline display(Markdown(...)) in a Quarto chunk."""
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def null_rank_rows(df: pd.DataFrame, scale_col: bool = True) -> list[list[str]]:
    """Rows of (scale, product, ρ product, ρ null, difference), larger ρ in bold."""
    label = {7: "~5 km² (res 7)", 8: "~0.7 km² (res 8)", 9: "~0.1 km² (res 9)"}
    rows = []
    for _, r in df.iterrows():
        a, b = f3(r.rho_product), f3(r.rho_null)
        if r.rho_product > r.rho_null: a = f"**{a}**"
        else: b = f"**{b}**"
        row = [label[int(r.res)]] if scale_col else []
        rows.append(row + [r["product"], a, b, signed(r.delta, f3)])
    return rows


# ---------------------------------------------------------------- core region: six products + rules (rq5b)
rq5b = {r: csv(f"RQ5-ensemble/rq5b_six_member{'' if r == 10 else f'_r{r}'}.csv").set_index("rule") for r in (10, 20, 30)}
core = rq5b[10]
prod = core.loc[PRODUCTS]
for p in PRODUCTS:
    N[f"core_P_{p}"] = f3(core.loc[p, "P_cems"])
    N[f"core_R_{p}"] = f2(core.loc[p, "R_cems"])
    N[f"core_F1_{p}"] = f3(core.loc[p, "F1_cems"])
    N[f"core_flags_{p}"] = com(core.loc[p, "flagged"])
    N[f"core_P20_{p}"] = f3(rq5b[20].loc[p, "P_cems"])
    N[f"core_P30_{p}"] = f3(rq5b[30].loc[p, "P_cems"])
N["core_P_range"] = rng(prod.P_cems.min(), prod.P_cems.max())            # was 0.045–0.093
N["core_P_range2"] = rng(prod.P_cems.min(), prod.P_cems.max(), f2)       # abstract: 0.05–0.09
N["core_R_range"] = rng(prod.R_cems.min(), prod.R_cems.max(), f2)        # was 0.31–0.69
N["core_F1_range"] = rng(prod.F1_cems.min(), prod.F1_cems.max(), f2)     # was 0.09–0.15
N["core_F1_best"] = f3(prod.F1_cems.max())
N["core_F1_best2"] = f2(prod.F1_cems.max())
N["core_F1_best_product"] = LONG[prod.F1_cems.idxmax()]
N["core_P_best_product"] = LONG[prod.P_cems.idxmax()]
N["core_P_worst_product"] = LONG[prod.P_cems.idxmin()]
N["core_fa_per_hit_range"] = f"{words(fa_per_hit(prod.P_cems.max()))} to {words(fa_per_hit(prod.P_cems.min()))}"  # was ten to twenty
# agreement rules
for k in range(1, 7):
    r = core.loc[f"{k}-of-6"]
    N[f"k{k}_P"] = f3(r.P_cems); N[f"k{k}_R"] = f2(r.R_cems); N[f"k{k}_F1"] = f3(r.F1_cems)
    N[f"k{k}_P_pct"] = pct(r.P_cems); N[f"k{k}_R_pct"] = pct(r.R_cems); N[f"k{k}_flags"] = com(r.flagged)
    N[f"k{k}_visits30"] = f"{r.flagged / (rq5b[30].loc[f'{k}-of-6', 'R_cems'] * N_CEMS_CORE):.1f}"
    N[f"k{k}_visits30_int"] = str(int(round(r.flagged / (rq5b[30].loc[f'{k}-of-6', 'R_cems'] * N_CEMS_CORE))))
better = core.loc[["4-of-6", "5-of-6"], "F1_cems"]
N["better_rules_F1_range"] = rng(better.min(), better.max(), f2)        # was 0.26–0.28
N["best_rule_F1"] = f3(core.loc[[f"{k}-of-6" for k in range(1, 7)], "F1_cems"].max())
N["best_rule"] = core.loc[[f"{k}-of-6" for k in range(1, 7)], "F1_cems"].idxmax()
N["best_rule_over_best_single"] = f"{core.loc[[f'{k}-of-6' for k in range(1, 7)], 'F1_cems'].max() / prod.F1_cems.max():.1f}"
for pair in ("IMPACT∧OSU", "MS∧UH", "MS∧LIST", "LIST∧UH", "UNEP∧OSU", "MS∧UNEP"):
    N[f"pair_P_{pair}"] = f3(core.loc[pair, "P_cems"])
    N[f"pair_F1_{pair}"] = f3(core.loc[pair, "F1_cems"])
N["pair_P_best"] = f3(core.loc[[r for r in core.index if "∧" in r], "P_cems"].max())
N["crowd_adj_P_range"] = rng(prod.P_crowd_adj.min(), prod.P_crowd_adj.max(), f2)

# ---------------------------------------------------------------- as delivered (rq2i)
rq2i = csv("RQ2-cems-footprint-points/rq2i_per_aoi_scorecard.csv")
asd = rq2i[rq2i.aoi == "ALL (as delivered)"].drop_duplicates("product").set_index("product")
for p in PRODUCTS:
    N[f"asd_P_{p}"] = f3(asd.loc[p, "P_cems"]); N[f"asd_R_{p}"] = f2(asd.loc[p, "R_cems"])
    N[f"asd_flags_{p}"] = com(asd.loc[p, "n_flags"]); N[f"asd_crowdcov_{p}"] = pct(asd.loc[p, "crowd_cov_of_fps"])
N["asd_P_min"] = f3(asd.P_cems.min()); N["asd_P_max"] = f3(asd.P_cems.max())
N["asd_P_min_product"] = LONG[asd.P_cems.idxmin()]; N["asd_P_max_product"] = LONG[asd.P_cems.idxmax()]
N["asd_UH_ratio"] = words(round(core.loc["UH", "P_cems"] / asd.loc["UH", "P_cems"]))
N["asd_P_sorted"] = ", ".join(f"{LONG[p]} {f3(asd.loc[p, 'P_cems'])}" for p in asd.P_cems.sort_values(ascending=False).index)
outside = rq2i[~rq2i.aoi.isin(["Caraballeda", "ALL (as delivered)"])]
N["outside_P_range"] = rng(outside.P_cems.min(), outside.P_cems.max(), f2)      # was 0.00–0.02
N["outside_crowdcov_max"] = pct(outside.crowd_cov_of_fps.max())                  # was 12%
N["moron_R_best"] = pct(outside[outside.aoi == "Moron"].R_cems.max())            # was 19%
N["moron_R_best_product"] = LONG[outside[outside.aoi == "Moron"].set_index("product").R_cems.idxmax()]
for aoi, p in (("Santa Cruz", "UH"), ("Caracas", "IMPACT"), ("Caracas", "UH")):
    r = one(rq2i, aoi=aoi, product=p)
    N[f"flags_{aoi.replace(' ', '')}_{p}"] = com(r.n_flags)
    N[f"flagshare_{aoi.replace(' ', '')}_{p}"] = pct(r.flag_share, 1)
for p in ("IMPACT", "LIST"):  # coherence products in Santa Cruz
    N[f"flagshare_SantaCruz_{p}"] = pct(one(rq2i, aoi="Santa Cruz", product=p).flag_share, 1)

# ---------------------------------------------------------------- precision bounds (rq2r)
rq2r = csv("RQ2-cems-footprint-points/rq2r_precision_bounds.csv").set_index("product")
for p in PRODUCTS:
    for c in ("P_floor", "P_grade", "P_crowd", "P_upper", "P_crowd_extrap", "P_upper_extrap"):
        N[f"{c}_{p}"] = f3(rq2r.loc[p, c])
    N[f"crowdcov_{p}"] = pct(rq2r.loc[p, "crowd_cov_of_fps"])
N["P_upper_max"] = f2(rq2r.P_upper.max()); N["P_upper_max3"] = f3(rq2r.P_upper.max())
N["P_upper_max_product"] = LONG[rq2r.P_upper.idxmax()]
N["P_grade_range"] = rng(rq2r.P_grade.min(), rq2r.P_grade.max(), f2)
N["P_upper_range"] = rng(rq2r.P_upper.min(), rq2r.P_upper.max(), f2)
N["crowd_fp_near_class1_range"] = rng(rq2r.crowd_fp_near_class1.min(), rq2r.crowd_fp_near_class1.max(), pct)  # was 10–17%

# ---------------------------------------------------------------- field reference (rq2_chatmap, rq2k)
cm = csv("RQ2-cems-footprint-points/rq2_chatmap_recall.csv").set_index("reference")
cems_row = cm.loc["CEMS {2,3}"]
N["cems_field_complete_pct"] = pct(cems_row.complete_r20)          # was 94%
N["cems_field_significant_pct"] = pct(cems_row.significant_r20)    # was 49%
N["field_missed_by_all_pct"] = pct(1 - cm.loc["≥1-of-4 votes", "recall_r20"])   # was "about 11%"
for p, lab in (("MS", "MS"), ("IMPACT", "IMPACT v2"), ("OSU", "OSU"), ("UH", "UH"), ("LIST", "LIST"), ("UNEP", "UNEP debris (core region)")):
    N[f"field_R20_{p}"] = f2(cm.loc[lab, "recall_r20"])
rq2k = csv("RQ2-cems-footprint-points/rq2k_field_union_precision.csv").set_index("product")
gain = rq2k.P_rel_gain.str.rstrip("%").str.lstrip("+").astype(float)
N["field_union_gain_range"] = f"{int(gain.min())}–{int(gain.max())}%"       # was 5–9%

# ---------------------------------------------------------------- learned fusion and geography null (rq8, rq8b)
rq8 = {r: csv(f"RQ8-learned-fusion/rq8_best_f1_r{r}.csv").set_index("predictor") for r in (10, 20, 30)}
for r, d in rq8.items():
    N[f"null_F1_r{r}"] = f3(d.loc["geography null (logistic)", "f1"])
    N[f"vote_F1_r{r}"] = f3(d.loc["flat k-of-6 voting", "f1"])
    N[f"fusion_F1_r{r}"] = f3(d.loc["weighted fusion", "f1"])
    pr = d[d.kind.str.startswith("product")]
    N[f"prod_F1_range_r{r}"] = rng(pr.f1.min(), pr.f1.max(), f2)
d10 = rq8[10]
N["null_F1"] = N["null_F1_r10"]; N["null_F1_2"] = f2(d10.loc["geography null (logistic)", "f1"])
N["null_P"] = f3(d10.loc["geography null (logistic)", "precision"]); N["null_R"] = f2(d10.loc["geography null (logistic)", "recall"])
N["null_rf_F1"] = f3(d10.loc["geography null (rand. forest)", "f1"])
N["vote_F1"] = N["vote_F1_r10"]; N["fusion_F1"] = N["fusion_F1_r10"]
N["vote_over_null"] = signed(d10.loc["flat k-of-6 voting", "f1"] - d10.loc["geography null (logistic)", "f1"])     # was +0.16
N["fusion_over_null"] = signed(d10.loc["weighted fusion", "f1"] - d10.loc["geography null (logistic)", "f1"])      # was +0.21
N["fusion_over_vote_pct"] = pct(d10.loc["weighted fusion", "f1"] / d10.loc["flat k-of-6 voting", "f1"] - 1)      # was 18%
N["vote_best_cut"] = f"{int(round(d10.loc['flat k-of-6 voting', 'n_flags'] and next(k for k in range(1, 7) if int(core.loc[f'{k}-of-6', 'flagged']) == int(d10.loc['flat k-of-6 voting', 'n_flags']))))}-of-6"
N["null_beats_n_products"] = words((pr := d10[d10.kind.str.startswith("product")]).f1.lt(d10.loc["geography null (logistic)", "f1"]).sum())
N["null_F1_by_radius"] = "/".join(N[f"null_F1_r{r}"] for r in (10, 20, 30))
N["vote_F1_by_radius"] = "/".join(N[f"vote_F1_r{r}"] for r in (10, 20, 30))
N["fusion_F1_by_radius"] = "/".join(N[f"fusion_F1_r{r}"] for r in (10, 20, 30))
rq8b = csv("RQ8-learned-fusion/rq8b_asdelivered_baseline_r10.csv").set_index("product")
for p in PRODUCTS:
    N[f"asd8_P_{p}"] = f3(rq8b.loc[p, "P_product"]); N[f"asd8_R_{p}"] = f2(rq8b.loc[p, "R_product"])
    N[f"dz_P_{p}"] = f3(rq8b.loc[p, "P_dayzero_matched"]); N[f"dz_R_{p}"] = f2(rq8b.loc[p, "R_dayzero_matched"])
    N[f"dz_R_pct_{p}"] = pct(rq8b.loc[p, "R_dayzero_matched"])
N["dz_beats_n"] = words((rq8b.P_dayzero_matched > rq8b.P_product).sum())
N["core_pos_r10"] = com(rq8b.loc["MS", "n_pos"])  # Microsoft's AOI ∩ CEMS is the core-region label set
rq8b20 = csv("RQ8-learned-fusion/rq8b_asdelivered_baseline_r20.csv").set_index("product")
N["core_pos_r20"] = com(rq8b20.loc["MS", "n_pos"])

# ---------------------------------------------------------------- confidence intervals (rq9)
ci = csv("RQ9-uncertainty/rq9_ci_core.csv")
cia = csv("RQ9-uncertainty/rq9_ci_asdelivered_r10.csv")
r = one(cia, rule="UH", metric="P")
N["asd_UH_P_lo"] = f3(r.lo); N["asd_UH_P_hi"] = f3(r.hi)
v6 = one(ci, rule="6-of-6", radius=30, metric="visits_per_find")  # visits/find is defined at the 30 m finding distance
N["k6_visits"] = f2(v6.point); N["k6_visits_hi"] = f2(v6.hi)
for p in PRODUCTS:
    r = one(ci, rule=p, radius=10, metric="P")
    N[f"ci_P_{p}"] = f"{f3(r.point)} ({f3(r.lo)}–{f3(r.hi)})"

# ---------------------------------------------------------------- ranking (rq3f, rq3g, rq3h, rq3b)
def _rq3():
    f_all = csv("RQ3-prioritization-error-structure/rq3f_null_ranking.csv")
    f_core = csv("RQ3-prioritization-error-structure/rq3f_null_ranking_core.csv")
    c8 = f_core[f_core.res == 8].set_index("product"); a7 = f_all[f_all.res == 7].set_index("product"); a8 = f_all[f_all.res == 8].set_index("product")
    N["rank_core8_range"] = rng(c8.rho_product.min(), c8.rho_product.max(), f2)        # was 0.48–0.74
    N["rank_asd7_range"] = f"{signed(a7.rho_product.min())} to {f2(a7.rho_product.max())}"  # was −0.09 to 0.59
    N["rank_asd8_range"] = f"{signed(a8.rho_product.min())} to {f2(a8.rho_product.max())}"
    for lab, key in (("Microsoft", "MS"), ("IMPACT v2", "IMPACT"), ("OSU", "OSU"), ("UH", "UH"), ("LIST", "LIST"), ("UNEP", "UNEP")):
        for tag, d in (("asd7", a7), ("asd8", a8), ("core8", c8)):
            if lab in d.index:
                N[f"rho_{tag}_{key}"] = f3(d.loc[lab, "rho_product"]); N[f"rhonull_{tag}_{key}"] = f3(d.loc[lab, "rho_null"])
    N["null_beats_n_asd7"] = words((a7.rho_null > a7.rho_product).sum()); N["null_beats_n_asd8"] = words((a8.rho_null > a8.rho_product).sum())
    N["asd_above_null_7"] = ", ".join(a7.index[a7.rho_product > a7.rho_null]) or "none"
    N["asd_above_null_8"] = ", ".join(a8.index[a8.rho_product > a8.rho_null]) or "none"
    N["asd_neg_7"] = ", ".join(f"{p} ({signed(v, f3)})" for p, v in a7.rho_product.items() if v < 0) or "none"
    N["_tbl_nullrank"] = md_table(null_rank_rows(pd.concat([f_all[f_all.res == 7], f_all[f_all.res == 8]])),
                                  ["scale", "product", "ρ product", "ρ geography null", "difference"])
    f_cara = csv("RQ3-prioritization-error-structure/rq3f_null_ranking_caraballeda.csv")
    c8c = f_cara[f_cara.res == 8].set_index("product"); c9c = f_cara[f_cara.res == 9].set_index("product")
    N["_tbl_nullrank_cara"] = md_table(null_rank_rows(f_cara[f_cara.res == 8].sort_values("delta", ascending=False), scale_col=False),
                                       ["product", "ρ product", "ρ geography null", "difference"])
    N["cara8_above"] = ", ".join(c8c.index[c8c.rho_product > c8c.rho_null]) or "none"
    N["cara8_below"] = ", ".join(c8c.index[c8c.rho_product <= c8c.rho_null]) or "none"
    N["cara8_n_above"] = words((c8c.rho_product > c8c.rho_null).sum()); N["cara9_n_above"] = words((c9c.rho_product > c9c.rho_null).sum())
    N["core8_above_null"] = ", ".join(c8.index[c8.rho_product > c8.rho_null]) or "none"
    N["core8_n_above"] = words((c8.rho_product > c8.rho_null).sum())
    h = csv("RQ3-prioritization-error-structure/rq3h_agreement_ranking.csv")
    h8 = h[h.res == 8].set_index("predictor")
    singles = [p for p in h8.index if "-of-" not in p and "fusion" not in p.lower() and "null" not in p.lower()]
    N["rank_best_single_rho"] = f2(h8.loc[singles, "rho"].max()); N["rank_best_single"] = h8.loc[singles, "rho"].idxmax()
    votes = [p for p in h8.index if "-of-" in p]
    N["rank_best_vote_rho"] = f2(h8.loc[votes, "rho"].max()); N["rank_best_vote"] = h8.loc[votes, "rho"].idxmax()
    for res in (8, 9):
        hr = h[h.res == res].set_index("predictor")
        sg = [p for p in hr.index if "-of-" not in p and "fusion" not in p.lower() and "null" not in p.lower()]
        vt = [p for p in hr.index if "-of-" in p]
        N[f"top20_single_{res}"] = str(int(round(20 * hr.loc[sg, "top20"].max())))
        N[f"top20_vote_{res}"] = str(int(round(20 * hr.loc[vt, "top20"].max())))
        N[f"top20_vote_rule_{res}"] = hr.loc[vt, "top20"].idxmax()
    g = csv("RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv")
    g8 = g[g.res == 8].set_index("product")
    N["frac_null_range8"] = rng(g8.rho_null_frac.min(), g8.rho_null_frac.max(), f2)   # was 0.43–0.65
    N["frac8_above_null"] = ", ".join(g8.index[g8.rho_frac > g8.rho_null_frac]) or "none"
    N["count8_above_null"] = ", ".join(g8.index[g8.rho_count > g8.rho_null_count]) or "none"
    for lab, key in (("IMPACT v2", "IMPACT"), ("Microsoft", "MS"), ("UH", "UH")):
        N[f"frac_count_{key}"] = f2(g8.loc[lab, "rho_count"]); N[f"frac_frac_{key}"] = f2(g8.loc[lab, "rho_frac"])
    b = csv("RQ3-prioritization-error-structure/rq3b_per_area_moran.csv")
    bc = b[(b.area == "Caraballeda") & b["product"].isin(["MS", "IMPACT", "OSU"])]
    N["moran_range"] = rng(bc.moran_I.min(), bc.moran_I.max(), f2)                 # was 0.45–0.60
    N["moran_p"] = f"{bc.p.max():.3f}"
    li = csv("RQ3-prioritization-error-structure/rq3d_lisa_summary.csv").set_index("product")
    ns_share = li.ns / li.cells
    N["lisa_ns_range"] = rng(ns_share.min(), ns_share.max(), pct)                   # was 78–86%


# ---------------------------------------------------------------- west strip, OSU versions, tiers (rq2o, rq2h, rq2p)
def _rq2_rest():
    o = csv("RQ2-cems-footprint-points/rq2o_uh_west_strip.csv")
    for p in ("MS", "UH"):
        for side in ("west", "east"):
            r = one(o, product=p, side=side)
            N[f"strip_share_{p}_{side}"] = pct(r.flag_share, 1); N[f"strip_P_{p}_{side}"] = f3(r.P_cems); N[f"strip_P2_{p}_{side}"] = f2(r.P_cems)
    h = csv("RQ2-cems-footprint-points/rq2h_osu_v0_v1.csv").set_index("version")
    N["osu_v0_P"] = f3(h.loc["v0 (common extent)", "P"]); N["osu_v1_P"] = f3(h.loc["v1 (common extent)", "P"])
    N["osu_v0_R"] = f2(h.loc["v0 (common extent)", "R"]); N["osu_v1_R"] = f2(h.loc["v1 (common extent)", "R"])
    t = csv("RQ2-cems-footprint-points/rq2p_osu_v1_tiers.csv")
    tc = t[t.region == "core region"].set_index("cut")
    N["osu_tier_high_P"] = f3(tc.loc["v1 high_confidence only", "P"]); N["osu_tier_prob_P"] = f3(tc.loc["v1 probable only", "P"])
    N["osu_tier_head_P"] = f3(tc.loc["v1 published headline (prob+high)", "P"])
    N["osu_tier_high_F1"] = f3(tc.loc["v1 high_confidence only", "F1"]); N["osu_tier_head_F1"] = f3(tc.loc["v1 published headline (prob+high)", "F1"])
    N["osu_tier_high_R"] = f2(tc.loc["v1 high_confidence only", "R"]); N["osu_tier_head_R"] = f2(tc.loc["v1 published headline (prob+high)", "R"])
    dn = csv("RQ2-cems-footprint-points/rq2_density_null.csv")
    for area, p in (("Santa Cruz", "IMPACT"), ("Santa Cruz", "OSU"), ("Santa Cruz", "UH"), ("Caracas", "IMPACT")):
        r = one(dn, area=area, product=p)
        N[f"dn_share_{area.replace(' ', '')}_{p}"] = f"{r.flag_pct:.1f}%"; N[f"dn_flags_{area.replace(' ', '')}_{p}"] = com(r.n_flag)


# ---------------------------------------------------------------- Microsoft confidence sweep (rq2_ms_confidence; native footprints)
def _ms_conf():
    c = csv("RQ2-cems-footprint-points/rq2_ms_confidence_curve.csv").sort_values("thresh")
    N["msconf_R_lo"] = f2(c.recall.iloc[-1]); N["msconf_R_hi"] = f2(c.recall.iloc[0])
    N["msconf_P_lo"] = f2(c.precision.iloc[0]); N["msconf_P_hi"] = f2(c.precision.iloc[-1])


# ---------------------------------------------------------------- flag totals and geography of flags (rq2s, rq2i)
def _flags():
    t = csv("RQ2-cems-footprint-points/rq2s_flag_totals.csv").set_index("product")
    for p in PRODUCTS:
        N[f"total_flags_{p}"] = com(t.loc[p, "total_flags"]); N[f"outside_cems_pct_{p}"] = pct(t.loc[p, "share_outside"])
    cara = rq2i[rq2i.aoi == "Caraballeda"].set_index("product")
    for p in PRODUCTS:
        share_out = 1 - cara.loc[p, "n_flags"] / asd.loc[p, "n_flags"]
        p_lost = 1 - asd.loc[p, "P_cems"] / cara.loc[p, "P_cems"]
        N[f"outcara_share_{p}"] = pct(share_out); N[f"outcara_plost_{p}"] = pct(max(p_lost, 0))
        N[f"cara_P_{p}"] = f3(cara.loc[p, "P_cems"])


# ---------------------------------------------------------------- radius ratio (rq5b r10 vs r30)
def _ratio():
    for r in (10, 20, 30):
        d = rq5b[r]; pr_ = d.loc[PRODUCTS]; rules = d.loc[[f"{k}-of-6" for k in range(1, 7)]]
        N[f"ratio_r{r}"] = f"{rules.F1_cems.max() / pr_.F1_cems.max():.1f}"


# ---------------------------------------------------------------- centroid -> polygon frame deltas (RQ0 native_rerun)
def _frame():
    f = csv("RQ0-matching-basis/native_rerun/shared_base_polygon_core.csv")
    f = f[(f.radius_m == 10) & f.rule.isin(["Microsoft", "IMPACT", "OSU", "UH", "LIST", "UNEP"])]
    dP = f.poly_P - f.centroid_P; dR = f.poly_R - f.centroid_R
    N["frame_dP_range"] = rng(dP.min(), dP.max(), f2); N["frame_dR_range"] = rng(dR.min(), dR.max(), f2)


# ---------------------------------------------------------------- crowd round 2 (rq7)
def _rq7():
    s = csv("RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv").set_index("product")
    N["r2_MS_unmatched"] = com(s.loc["MS", "strip_unmatched_flags"])
    N["r2_MS_conf_r1"] = pct(s.loc["MS", "unmatched_conf_share_r1"], 1); N["r2_MS_conf_r2"] = pct(s.loc["MS", "unmatched_conf_share_r2"], 1)
    N["r2_MS_one_in"] = words(round(1 / s.loc["MS", ["unmatched_conf_share_r1", "unmatched_conf_share_r2"]].mean()))
    for p in ("MS", "UNEP", "IMPACT"):
        N[f"r2_padj_r1_{p}"] = f3(s.loc[p, "P_crowd_adj_r1"]); N[f"r2_padj_r2_{p}"] = f3(s.loc[p, "P_crowd_adj_r2swap"])
    N["r2_padj_maxdelta"] = f2(s.delta.abs().max())
    rep = csv("RQ7-mapswipe-validation/rq7_round2_replication.csv").set_index("metric").value
    N["r2_cells"] = com(rep["paired_task_cells"])


for _fn in (_rq3, _rq2_rest, _ms_conf, _flags, _ratio, _frame, _rq7):
    try:
        _fn()
    except FileNotFoundError as e:  # a not-yet-regenerated artefact: fail at render, loudly
        raise RuntimeError(f"brief_numbers: {e}") from e

if __name__ == "__main__":
    import sys
    keys = sys.argv[1:] or sorted(N)
    for k in keys:
        print(f"{k:32s} {N[k]}")
