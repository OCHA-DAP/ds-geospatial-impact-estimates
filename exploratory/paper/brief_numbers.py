"""Single source for every number quoted in manuscript_brief.qmd (ADR-0030).

The brief's prose reads values inline as `{python} N["key"]`; nothing numeric is typed by
hand. Every key below is a lookup on artefacts/results.csv (region, lens, radius, predictor, metric), so a refreeze of the artefact
tree re-points the brief on the next render, and an auditor can trace any figure in the
text to one CSV cell. Missing rows or files raise; there are no fallbacks.

Usage in the .qmd (one setup chunk, `#| include: false`):
    import sys; sys.path.insert(0, ".")
    from brief_numbers import N
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

A = pathlib.Path(__file__).parent
PRODUCTS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
LONG = {"MS": "Microsoft", "IMPACT": "IMPACT", "OSU": "OSU", "UH": "UH", "LIST": "LIST", "UNEP": "UNEP"}
ORDER = ["Microsoft", "IMPACT v2", "OSU", "UH", "LIST", "UNEP"]  # delivery order, used wherever products are listed


def ordered(names) -> list:
    return sorted(names, key=lambda n: ORDER.index(n) if n in ORDER else 99)


class Numbers(dict):
    def __missing__(self, key):
        raise KeyError(f"brief_numbers: no key {key!r} — define it in brief_numbers.py")


N = Numbers()


# ---------------------------------------------------------------- helpers
RESULTS = A / "results.csv"   # exploratory/paper/results.csv


def results() -> pd.DataFrame:
    if not RESULTS.exists():
        raise FileNotFoundError("results.csv missing — run `snakemake results` (pipeline/consolidate.py)")
    return pd.read_csv(RESULTS)


_R = results()
_R["radius"] = _R["radius"].fillna(-1)   # sentinel for "no radius" (facts, flag totals, round-2 metrics)
N_CEMS_CORE = int(_R[(_R.lens == "facts") & (_R.region == "core") & (_R.predictor == "CEMS") & (_R.metric == "n_points_2_3")].value.iloc[0])  # core CEMS grade-2/3 points


def W(region=None, lens=None, radius="any", source=None, index="predictor") -> pd.DataFrame:
    """Wide slice of results.csv (rows = predictor, columns = metric). radius=None selects rows
    with no radius; radius="any" does not filter on it."""
    m = pd.Series(True, index=_R.index)
    if region is not None: m &= _R.region == region
    if lens is not None: m &= _R.lens == lens
    if radius is None: m &= _R.radius == -1
    elif radius != "any": m &= _R.radius == radius
    if source is not None: m &= _R.source.str.contains(source, regex=False)
    sub = _R[m]
    if not len(sub):
        raise KeyError(f"results.csv has no rows for region={region} lens={lens} radius={radius} source={source}")
    idx = [index] if isinstance(index, str) else list(index)
    return sub.pivot_table(index=idx, columns="metric", values="value", aggfunc="first")


def L(region=None, lens=None, source=None) -> pd.DataFrame:
    """Wide with region/radius/predictor kept as columns (per-resolution or per-region frames)."""
    m = pd.Series(True, index=_R.index)
    if region is not None: m &= _R.region == region
    if lens is not None: m &= _R.lens == lens
    if source is not None: m &= _R.source.str.contains(source, regex=False)
    sub = _R[m]
    if not len(sub):
        raise KeyError(f"results.csv has no rows for region={region} lens={lens} source={source}")
    w = sub.pivot_table(index=["region", "radius", "predictor"], columns="metric", values="value", aggfunc="first").reset_index()
    w["radius"] = w["radius"].replace(-1, np.nan)
    return w


def tbl(region: str, lens: str, radius, index: str = "predictor") -> pd.DataFrame:
    """Wide slice of results.csv: rows = predictor, columns = metric, for one region/lens/radius."""
    m = (_R.region == region) & (_R.lens == lens) & (_R.radius == radius)
    sub = _R[m]
    if not len(sub):
        raise KeyError(f"results.csv has no rows for {region}/{lens}/{radius}")
    return sub.pivot(index=index, columns="metric", values="value")


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
def _rq5b(r):
    t = tbl("core", "points", r).rename(columns={"P": "P_cems", "R": "R_cems", "F1": "F1_cems", "n_flags": "flagged", "R_field20": "R_field_r20"})
    if r == 10:
        c = tbl("core", "crowd", 10).rename(columns={"crowd_cov": "crowd_cov_of_fps", "fp_crowd_damaged": "FP_crowd_damaged"})
        t = t.join(c)
    return t
rq5b = {r: _rq5b(r) for r in (10, 20, 30)}
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
    # flags per CONFIRMED damaged building = 1/precision, same 10 m frame as the rest of the dial sentence.
    # (The visits30 form above divides flags by expert POINTS reached and can fall below 1 for strict rules,
    # because one flagged building can sit within 30 m of several points; kept for the CI table.)
    N[f"k{k}_visits10_int"] = str(int(round(1 / r.P_cems)))
better = core.loc[["4-of-6", "5-of-6"], "F1_cems"]
N["better_rules_F1_range"] = rng(better.min(), better.max(), f2)        # was 0.26–0.28
N["best_rule_F1"] = f3(core.loc[[f"{k}-of-6" for k in range(1, 7)], "F1_cems"].max())
N["best_rule"] = core.loc[[f"{k}-of-6" for k in range(1, 7)], "F1_cems"].idxmax()
N["best_rule_over_best_single"] = f"{core.loc[[f'{k}-of-6' for k in range(1, 7)], 'F1_cems'].max() / prod.F1_cems.max():.1f}"
_pairs = core.loc[[r for r in core.index if "∧" in r]]
for pair in _pairs.index:
    N[f"pair_P_{pair}"] = f3(core.loc[pair, "P_cems"])
    N[f"pair_F1_{pair}"] = f3(core.loc[pair, "F1_cems"])
N["pair_n"] = str(len(_pairs))
N["pair_P_best"] = f3(_pairs.P_cems.max()); N["pair_best"] = _pairs.P_cems.idxmax().replace("∧", " and ")
N["pair_P_worst"] = f3(_pairs.P_cems.min()); N["pair_worst"] = _pairs.P_cems.idxmin().replace("∧", " and ")
N["pair_P_range_ex"] = rng(_pairs.P_cems.drop([_pairs.P_cems.idxmax(), _pairs.P_cems.idxmin()]).min(),
                          _pairs.P_cems.drop([_pairs.P_cems.idxmax(), _pairs.P_cems.idxmin()]).max(), f2)
# sensing modality per product (Table 1): two VHR-optical + AI products, four Sentinel-1 radar products
_OPTICAL = {"MS", "UH"}
_is_radar_pair = [set(r.split("∧")).isdisjoint(_OPTICAL) for r in _pairs.index]
_radar = _pairs[_is_radar_pair]; _mixed_or_optical = _pairs[[not x for x in _is_radar_pair]]
N["pair_radar_n"] = words(len(_radar)); N["pair_radar_P_range"] = rng(_radar.P_cems.min(), _radar.P_cems.max(), f2)
_PAIR_P_THRESH = 0.3
N["pair_P_thresh"] = f"{_PAIR_P_THRESH:.1f}"
N["pair_P_above_thresh_n"] = words(int((_pairs.P_cems > _PAIR_P_THRESH).sum()))
# The recommendation paragraph states these two facts in words. If a refreeze breaks either, fail the
# build here rather than publish a sentence the data no longer supports.
_bottom3 = _pairs.P_cems.nsmallest(3).index
if not all(set(r.split("∧")).isdisjoint(_OPTICAL) for r in _bottom3):
    raise AssertionError(f"brief says the three weakest pairs are all radar-radar; now {list(_bottom3)} — reword the recommendation")
_above = _pairs.index[_pairs.P_cems > _PAIR_P_THRESH]
if not all(not set(r.split("∧")).isdisjoint(_OPTICAL) for r in _above):
    raise AssertionError(f"brief says every pair above P {_PAIR_P_THRESH} has an optical member; now {list(_above)} — reword the recommendation")
if set(_pairs.P_cems.idxmax().split("∧")) <= _OPTICAL or set(_pairs.P_cems.idxmax().split("∧")).isdisjoint(_OPTICAL):
    raise AssertionError(f"brief says the best pair mixes optical and radar; now {_pairs.P_cems.idxmax()} — reword the recommendation")
_second = _pairs.P_cems.drop(_pairs.P_cems.idxmax()).idxmax()
N["pair_second"] = _second.replace("∧", " and "); N["pair_P_second"] = f3(_pairs.loc[_second, "P_cems"])
for _r in _pairs.index:
    N[f"pair_P2_{_r}"] = f2(_pairs.loc[_r, "P_cems"])
N["crowd_adj_P_range"] = rng(prod.P_crowd.min(), prod.P_crowd.max(), f2)

# ---------------------------------------------------------------- as delivered (rq2i)
def _rq2i():
    AOIS = ["asd", "Caraballeda", "Moron", "San Felipe", "Caracas", "Santa Cruz"]   # the as-delivered frame and the CEMS AOIs
    sub = _R[(_R.lens.isin(["points", "crowd"])) & (_R.radius == 10) & (_R.region.isin(AOIS))]
    w = sub.pivot_table(index=["region", "predictor"], columns="metric", values="value").reset_index()
    w = w.rename(columns={"region": "aoi", "predictor": "product", "P": "P_cems", "R": "R_cems", "crowd_cov": "crowd_cov_of_fps"})
    w["aoi"] = w["aoi"].replace({"asd": "ALL (as delivered)"})
    return w
rq2i = _rq2i()
asd = rq2i[rq2i.aoi == "ALL (as delivered)"].drop_duplicates("product").set_index("product")
for p in PRODUCTS:
    N[f"asd_P_{p}"] = f3(asd.loc[p, "P_cems"]); N[f"asd_R_{p}"] = f2(asd.loc[p, "R_cems"])
    N[f"asd_flags_{p}"] = com(asd.loc[p, "n_flags"]); N[f"asd_crowdcov_{p}"] = pct(asd.loc[p, "crowd_cov_of_fps"])
    N[f"asd_bld_{p}"] = com(asd.loc[p, "n_bld"])
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
rq2r = W("core", "bounds", 10).rename(columns={"crowd_cov": "crowd_cov_of_fps"})
for p in PRODUCTS:
    for c in ("P_floor", "P_grade", "P_crowd", "P_upper"):
        N[f"{c}_{p}"] = f3(rq2r.loc[p, c])
    N[f"crowdcov_{p}"] = pct(rq2r.loc[p, "crowd_cov_of_fps"])
N["P_upper_max"] = f2(rq2r.P_upper.max()); N["P_upper_max3"] = f3(rq2r.P_upper.max())
N["P_upper_max_product"] = LONG[rq2r.P_upper.idxmax()]
N["P_grade_range"] = rng(rq2r.P_grade.min(), rq2r.P_grade.max(), f2)
N["P_upper_range"] = rng(rq2r.P_upper.min(), rq2r.P_upper.max(), f2)
N["crowd_fp_near_class1_range"] = rng(rq2r.crowd_fp_near_class1.min(), rq2r.crowd_fp_near_class1.max(), pct)  # was 10–17%

# ---------------------------------------------------------------- field reference (rq2_chatmap, rq2k)
_f = L("field", "field")
cm = pd.DataFrame({"recall_r20": _f[_f.radius == 20].set_index("predictor")["R"], "recall_r10": _f[_f.radius == 10].set_index("predictor")["R"],
                   "complete_r20": _f[_f.radius == 20].set_index("predictor")["R_complete"], "significant_r20": _f[_f.radius == 20].set_index("predictor")["R_significant"]})
cems_row = cm.loc["CEMS {2,3}"]
N["cems_field_complete_pct"] = pct(cems_row.complete_r20)          # was 94%
N["cems_field_significant_pct"] = pct(cems_row.significant_r20)    # was 49%
N["field_missed_by_all_pct"] = pct(1 - cm.loc["≥1-of-4 votes", "recall_r20"])   # was "about 11%"; four products (MS, IMPACT, OSU, UH) inside their common extent
N["field_missed_by_all6_pct"] = pct(1 - cm.loc["≥1-of-6 votes (core region)", "recall_r20"])   # all six products, core region
for p, lab in (("MS", "MS"), ("IMPACT", "IMPACT v2"), ("OSU", "OSU"), ("UH", "UH"), ("LIST", "LIST"), ("UNEP", "UNEP debris (core region)")):
    N[f"field_R20_{p}"] = f2(cm.loc[lab, "recall_r20"])
rq2k = W("core", "field-union", 10)
gain = rq2k.P_rel_gain
N["field_union_gain_range"] = f"{int(gain.min())}–{int(gain.max())}%"       # was 5–9%

# ---------------------------------------------------------------- learned fusion and geography null (rq8, rq8b)
rq8 = {r: W("core", "labels", r).rename(columns={"P": "precision", "R": "recall", "F1": "f1"}) for r in (10, 20, 30)}
for r, d in rq8.items():
    N[f"null_F1_r{r}"] = f3(d.loc["geography null (logistic)", "f1"])
    N[f"vote_F1_r{r}"] = f3(d.loc["flat k-of-6 voting", "f1"])
    N[f"fusion_F1_r{r}"] = f3(d.loc["weighted fusion", "f1"])
    pr = d.loc[PRODUCTS]
    N[f"prod_F1_range_r{r}"] = rng(pr.f1.min(), pr.f1.max(), f2)
d10 = rq8[10]
N["null_F1"] = N["null_F1_r10"]; N["null_F1_2"] = f2(d10.loc["geography null (logistic)", "f1"])
# covariate ablation of the null (rq8d, frozen): density-only vs the weakest product at 10 m
_abl = W("core", "labels-ablation", 10)
N["dens_only_F1"] = f2(_abl.loc["dens", "F1"]); N["prod_F1_min_r10"] = f2(d10.loc[PRODUCTS, "f1"].min())
_gap = d10.loc[PRODUCTS, "f1"].min() - _abl.loc["dens", "F1"]
N["dens_vs_band"] = ("inside the six products' performance band" if _gap <= 0
                     else f"within {_gap:.2f} of the bottom of the six products' performance band")
N["dem_variant_F1"] = f2(_abl.loc["dens+elev+mmi", "F1"])
N["null_P"] = f3(d10.loc["geography null (logistic)", "precision"]); N["null_R"] = f2(d10.loc["geography null (logistic)", "recall"])
N["null_rf_F1"] = f3(d10.loc["geography null (rand. forest)", "f1"])
N["vote_F1"] = N["vote_F1_r10"]; N["fusion_F1"] = N["fusion_F1_r10"]
N["vote_over_null"] = signed(d10.loc["flat k-of-6 voting", "f1"] - d10.loc["geography null (logistic)", "f1"])     # was +0.16
N["fusion_over_null"] = signed(d10.loc["weighted fusion", "f1"] - d10.loc["geography null (logistic)", "f1"])      # was +0.21
N["fusion_over_vote_pct"] = pct(d10.loc["weighted fusion", "f1"] / d10.loc["flat k-of-6 voting", "f1"] - 1)      # was 18%
N["vote_best_cut"] = f"{int(round(d10.loc['flat k-of-6 voting', 'n_flags'] and next(k for k in range(1, 7) if int(core.loc[f'{k}-of-6', 'flagged']) == int(d10.loc['flat k-of-6 voting', 'n_flags']))))}-of-6"
N["null_beats_n_products"] = words(d10.loc[PRODUCTS].f1.lt(d10.loc["geography null (logistic)", "f1"]).sum())
N["null_F1_by_radius"] = "/".join(N[f"null_F1_r{r}"] for r in (10, 20, 30))
N["vote_F1_by_radius"] = "/".join(N[f"vote_F1_r{r}"] for r in (10, 20, 30))
N["fusion_F1_by_radius"] = "/".join(N[f"fusion_F1_r{r}"] for r in (10, 20, 30))
_rn8b = {"P": "P_product", "R": "R_product", "P_dayzero": "P_dayzero_matched", "R_dayzero": "R_dayzero_matched"}
rq8b = W("asd", "labels", 10).rename(columns=_rn8b)
for p in PRODUCTS:
    N[f"asd8_P_{p}"] = f3(rq8b.loc[p, "P_product"]); N[f"asd8_R_{p}"] = f2(rq8b.loc[p, "R_product"])
    N[f"dz_P_{p}"] = f3(rq8b.loc[p, "P_dayzero_matched"]); N[f"dz_R_{p}"] = f2(rq8b.loc[p, "R_dayzero_matched"])
    N[f"dz_R_pct_{p}"] = pct(rq8b.loc[p, "R_dayzero_matched"])
N["dz_beats_n"] = words((rq8b.P_dayzero_matched > rq8b.P_product).sum())
N["dz_UH_P_ratio"] = f"{rq8b.loc['UH', 'P_dayzero_matched'] / rq8b.loc['UH', 'P_product']:.1f}"
N["core_pos_r10"] = com(rq8b.loc["MS", "n_pos"])  # Microsoft's AOI ∩ CEMS is the core-region label set
rq8b20 = W("asd", "labels", 20).rename(columns=_rn8b)
N["core_pos_r20"] = com(rq8b20.loc["MS", "n_pos"])

# ---------------------------------------------------------------- confidence intervals (rq9)
def _ci(region, lens="ci", name="rule"):
    """rq9's long form again: rule|predictor, radius, metric, point, lo, hi."""
    w = L(region, lens); out = []
    for _, row in w.iterrows():
        for m in [c for c in w.columns if c not in ("region", "radius", "predictor") and not c.endswith(("_lo", "_hi"))]:
            if pd.notna(row[m]):
                out.append({name: row.predictor, "radius": int(row.radius), "metric": m, "point": row[m], "lo": row.get(f"{m}_lo"), "hi": row.get(f"{m}_hi")})
    return pd.DataFrame(out)
ci = _ci("core")
cia = _ci("asd")
ci_models = _ci("core", "ci-labels", name="predictor")  # rq9 model-frame intervals (tbl-ci-models)
r = one(cia, rule="UH", metric="P")
N["asd_UH_P_lo"] = f3(r.lo); N["asd_UH_P_hi"] = f3(r.hi)
v6 = one(ci, rule="6-of-6", radius=30, metric="visits_per_find")  # visits/find is defined at the 30 m finding distance
N["k6_visits"] = f2(v6.point); N["k6_visits_hi"] = f2(v6.hi)
for p in PRODUCTS:
    r = one(ci, rule=p, radius=10, metric="P")
    N[f"ci_P_{p}"] = f"{f3(r.point)} ({f3(r.lo)}–{f3(r.hi)})"

# ---------------------------------------------------------------- ranking (rq3f, rq3g, rq3h, rq3b)
def _rq3():
    def _f(region):
        w = L(region, "cells").rename(columns={"radius": "res", "predictor": "product", "rho": "rho_product", "top20": "top20_product"})
        w["res"] = w["res"].astype(int)
        w["_o"] = w["product"].map(lambda n: ORDER.index(n) if n in ORDER else 99)
        return w.sort_values(["res", "_o"], ascending=[False, True]).drop(columns="_o").reset_index(drop=True)
    f_all, f_core = _f("asd"), _f("core")
    c8 = f_core[f_core.res == 8].set_index("product"); a7 = f_all[f_all.res == 7].set_index("product"); a8 = f_all[f_all.res == 8].set_index("product")
    N["rank_core8_range"] = rng(c8.rho_product.min(), c8.rho_product.max(), f2)        # was 0.48–0.74
    N["rank_asd7_range"] = f"{signed(a7.rho_product.min())} to {f2(a7.rho_product.max())}"  # was −0.09 to 0.59
    N["rank_asd8_range"] = f"{signed(a8.rho_product.min())} to {f2(a8.rho_product.max())}"
    for lab, key in (("Microsoft", "MS"), ("IMPACT v2", "IMPACT"), ("OSU", "OSU"), ("UH", "UH"), ("LIST", "LIST"), ("UNEP", "UNEP")):
        for tag, d in (("asd7", a7), ("asd8", a8), ("core8", c8)):
            if lab in d.index:
                N[f"rho_{tag}_{key}"] = f3(d.loc[lab, "rho_product"]); N[f"rhonull_{tag}_{key}"] = f3(d.loc[lab, "rho_null"])
    N["null_beats_n_asd7"] = words((a7.rho_null > a7.rho_product).sum()); N["null_beats_n_asd8"] = words((a8.rho_null > a8.rho_product).sum())
    N["asd_above_null_7"] = ", ".join(ordered(a7.index[a7.rho_product > a7.rho_null])) or "none"
    N["asd_above_null_8"] = ", ".join(ordered(a8.index[a8.rho_product > a8.rho_null])) or "none"
    N["asd_neg_7"] = ", ".join(f"{p} ({signed(v, f3)})" for p, v in a7.rho_product.items() if v < 0) or "none"
    N["_tbl_nullrank"] = md_table(null_rank_rows(pd.concat([f_all[f_all.res == 7], f_all[f_all.res == 8]])),
                                  ["scale", "product", "ρ product", "ρ geography null", "difference"])
    f_cara = _f("Caraballeda")
    c8c = f_cara[f_cara.res == 8].set_index("product"); c9c = f_cara[f_cara.res == 9].set_index("product")
    N["_tbl_nullrank_cara"] = md_table(null_rank_rows(f_cara[f_cara.res == 8].sort_values("delta", ascending=False), scale_col=False),
                                       ["product", "ρ product", "ρ geography null", "difference"])
    N["cara8_above"] = ", ".join(ordered(c8c.index[c8c.rho_product > c8c.rho_null])) or "none"
    N["cara8_below"] = ", ".join(ordered(c8c.index[c8c.rho_product <= c8c.rho_null])) or "none"
    N["cara8_n_above"] = words((c8c.rho_product > c8c.rho_null).sum()); N["cara9_n_above"] = words((c9c.rho_product > c9c.rho_null).sum())
    N["core8_above_null"] = ", ".join(ordered(c8.index[c8.rho_product > c8.rho_null])) or "none"
    N["core8_n_above"] = words((c8.rho_product > c8.rho_null).sum())
    # within-damage-zone test in the CORE region (the brief's own frame; replaces the retired Caraballeda-AOI table)
    c9 = f_core[f_core.res == 9].set_index("product")
    N["_tbl_nullrank_core"] = md_table(null_rank_rows(f_core[f_core.res == 8].sort_values("delta", ascending=False), scale_col=False),
                                       ["product", "ρ product", "ρ geography null", "difference"])
    N["core8_below_null"] = ", ".join(ordered(c8.index[c8.rho_product <= c8.rho_null])) or "none"
    N["core9_n_above"] = words((c9.rho_product > c9.rho_null).sum())
    h = L("core", "cells-agreement").rename(columns={"radius": "res"}); h["res"] = h["res"].astype(int)
    h8 = h[h.res == 8].set_index("predictor")
    SINGLE = {"Microsoft", "IMPACT v2", "OSU", "UH", "LIST", "UNEP"}
    singles = [p for p in h8.index if p in SINGLE]
    N["rank_best_single_rho"] = f2(h8.loc[singles, "rho"].max()); N["rank_best_single"] = h8.loc[singles, "rho"].idxmax()
    votes = [p for p in h8.index if "-of-" in p]
    N["rank_best_vote_rho"] = f2(h8.loc[votes, "rho"].max()); N["rank_best_vote"] = h8.loc[votes, "rho"].idxmax()
    for res in (8, 9):
        hr = h[h.res == res].set_index("predictor")
        sg = [p for p in hr.index if p in SINGLE]
        vt = [p for p in hr.index if "-of-" in p]
        N[f"top20_single_{res}"] = str(int(round(20 * hr.loc[sg, "top20"].max())))
        N[f"top20_vote_{res}"] = str(int(round(20 * hr.loc[vt, "top20"].max())))
        N[f"top20_vote_rule_{res}"] = hr.loc[vt, "top20"].idxmax()
    g = L("asd", "cells-fraction").rename(columns={"radius": "res", "predictor": "product"}); g["res"] = g["res"].astype(int)
    g8 = g[g.res == 8].set_index("product")
    N["frac_null_range8"] = rng(g8.rho_null_frac.min(), g8.rho_null_frac.max(), f2)   # was 0.43–0.65
    N["frac8_above_null"] = ", ".join(ordered(g8.index[g8.rho_frac > g8.rho_null_frac])) or "none"
    N["count8_above_null"] = ", ".join(ordered(g8.index[g8.rho_count > g8.rho_null_count])) or "none"
    for lab, key in (("IMPACT v2", "IMPACT"), ("Microsoft", "MS"), ("UH", "UH")):
        N[f"frac_count_{key}"] = f2(g8.loc[lab, "rho_count"]); N[f"frac_frac_{key}"] = f2(g8.loc[lab, "rho_frac"])
    b = L(lens="moran").rename(columns={"region": "area", "predictor": "product"})
    bc = b[(b.area == "Caraballeda") & b["product"].isin(["MS", "IMPACT", "OSU"])]
    N["moran_range"] = rng(bc.moran_I.min(), bc.moran_I.max(), f2)                 # was 0.45–0.60
    N["moran_p"] = f"{bc.p.max():.3f}"
    li = W("asd", "lisa", 8)
    ns_share = li.ns / li.cells
    N["lisa_ns_range"] = rng(ns_share.min(), ns_share.max(), pct)                   # was 78–86%


# ---------------------------------------------------------------- west strip, OSU versions, tiers (rq2o, rq2h, rq2p)
def _rq2_rest():
    o = L(lens="points"); o = o[o.region.str.startswith("strip-")].rename(columns={"predictor": "product", "P": "P_cems"}); o["side"] = o.region.str.replace("strip-", "")
    for p in ("MS", "UH"):
        for side in ("west", "east"):
            r = one(o, product=p, side=side)
            N[f"strip_share_{p}_{side}"] = pct(r.flag_share, 1); N[f"strip_P_{p}_{side}"] = f3(r.P_cems); N[f"strip_P2_{p}_{side}"] = f2(r.P_cems)
    h = W("osu-versions", "points", 10)
    N["osu_v0_P"] = f3(h.loc["v0 (common extent)", "P"]); N["osu_v1_P"] = f3(h.loc["v1 (common extent)", "P"])
    N["osu_v0_R"] = f2(h.loc["v0 (common extent)", "R"]); N["osu_v1_R"] = f2(h.loc["v1 (common extent)", "R"])
    tc = W("osu-tiers:core region", "points", 10)
    N["osu_tier_high_P"] = f3(tc.loc["v1 high_confidence only", "P"]); N["osu_tier_prob_P"] = f3(tc.loc["v1 probable only", "P"])
    N["osu_tier_head_P"] = f3(tc.loc["v1 published headline (prob+high)", "P"])
    N["osu_tier_high_F1"] = f3(tc.loc["v1 high_confidence only", "F1"]); N["osu_tier_head_F1"] = f3(tc.loc["v1 published headline (prob+high)", "F1"])
    N["osu_tier_high_R"] = f2(tc.loc["v1 high_confidence only", "R"]); N["osu_tier_head_R"] = f2(tc.loc["v1 published headline (prob+high)", "R"])
    dn = L(lens="density").rename(columns={"region": "area", "predictor": "product"})
    for area, p in (("Santa Cruz", "IMPACT"), ("Santa Cruz", "OSU"), ("Santa Cruz", "UH"), ("Caracas", "IMPACT")):
        r = one(dn, area=area, product=p)
        N[f"dn_share_{area.replace(' ', '')}_{p}"] = f"{r.flag_pct:.1f}%"; N[f"dn_flags_{area.replace(' ', '')}_{p}"] = com(r.n_flag)


# ---------------------------------------------------------------- Microsoft confidence sweep (rq2_ms_confidence; native footprints)
def _ms_conf():
    c = W("ms-aoi", "confidence", 10).reset_index(); c["thresh"] = c.predictor.str.replace("thresh=", "").astype(float)
    c = c.sort_values("thresh").rename(columns={"R": "recall", "P": "precision"})
    N["msconf_R_lo"] = f2(c.recall.iloc[-1]); N["msconf_R_hi"] = f2(c.recall.iloc[0])
    N["msconf_P_lo"] = f2(c.precision.iloc[0]); N["msconf_P_hi"] = f2(c.precision.iloc[-1])


# ---------------------------------------------------------------- flag totals and geography of flags (rq2s, rq2i)
def _flags():
    t = W("all", "flags", None)
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
    f = W("core", "frame", 10).loc[["Microsoft", "IMPACT", "OSU", "UH", "LIST", "UNEP"]]
    dP = f.poly_P - f.centroid_P; dR = f.poly_R - f.centroid_R
    N["frame_dP_range"] = rng(dP.min(), dP.max(), f2); N["frame_dR_range"] = rng(dR.min(), dR.max(), f2)
    # gold's intersect mapping flagged this many core buildings for Microsoft (frame CSV, pre-ADR-0030); the 1:1 count is the points lens
    fr = W("core", "frame", 10)
    N["bleed_MS"] = pct(fr.loc["Microsoft", "flags_centroid"] / W("core", "points", 10).loc["MS", "n_flags"] - 1)


# ---------------------------------------------------------------- facts (pipeline/facts.py): geography, inputs, spacing, versions
def _facts():
    F = W(lens="facts", radius=None, index=["region", "predictor"])
    def f(region, predictor, metric): return float(F.loc[(region, predictor), metric])
    N["core_area_km2"] = f"{f('core', 'region', 'area_km2'):.0f}"; N["core_area_km2_1"] = f"{f('core', 'region', 'area_km2'):.1f}"
    N["core_n_buildings"] = com(f("core", "region", "n_buildings"))
    for p in ("MS", "IMPACT", "OSU", "UH", "LIST"):   # Table 1's analysis scope (UNEP publishes no extent)
        N[f"scope_bld_{p}"] = com(f("all", p, "scope_buildings")); N[f"scope_km2_{p}"] = com(f("all", p, "aoi_km2"))
    for p in ("MS", "UNEP", "UH"):   # appendix: delivered footprints falling in each frame
        N[f"native_asd_{p}"] = com(f("asd", p, "native_footprints")); N[f"native_core_{p}"] = com(f("core", p, "native_footprints"))
        N[f"iou_{p}"] = com(f("all", p, "mapped_by_iou"))
    N["products_overlap_km2"] = f"{f('all', 'region', 'products_overlap_km2'):.0f}"
    N["ms_aoi_km2"] = f"{f('all', 'MS', 'aoi_km2'):.0f}"
    N["core_cems"] = com(f("core", "CEMS", "n_points_2_3")); N["core_destroyed"] = com(f("core", "CEMS", "n_destroyed")); N["core_damaged"] = com(f("core", "CEMS", "n_damaged"))
    N["cems_total_2_3"] = com(f("all", "CEMS", "n_points_2_3"))
    for aoi, key in (("Caraballeda", "cara"), ("Moron", "moron"), ("San Felipe", "sanfelipe"), ("Caracas", "caracas"), ("Santa Cruz", "santacruz")):
        N[f"{key}_points"] = com(f(aoi, "CEMS", "n_points_2_3"))
    N["cara_share_pct"] = pct(f("Caraballeda", "CEMS", "share_of_points_2_3"))
    N["spacing_median_m"] = f"{f('core', 'spacing', 'median_nn_m'):.1f}"; N["spacing_within20_pct"] = pct(f("core", "spacing", "share_nn_within_20m"))
    N["h3_res7_km2"] = f"{f('all', 'h3-res7', 'avg_area_km2'):.1f}"; N["h3_res7_km2_0"] = f"{f('all', 'h3-res7', 'avg_area_km2'):.0f}"
    N["h3_res8_km2"] = f"{f('all', 'h3-res8', 'avg_area_km2'):.2f}"; N["h3_res8_km2_1"] = f"{f('all', 'h3-res8', 'avg_area_km2'):.1f}"
    N["h3_res9_km2"] = f"{f('all', 'h3-res9', 'avg_area_km2'):.1f}"
    N["ms_obscured_pct"] = pct(f("all", "MS", "share_mostly_obscured"), 1); N["ms_footprints"] = com(f("all", "MS", "n_footprints"))
    N["disha_extent_km2"] = f"{f('core', 'DISHA', 'extent_km2'):.1f}"; N["disha_covers_km2"] = f"{f('core', 'DISHA', 'covers_km2'):.1f}"
    N["disha_share_pct"] = pct(f("core", "DISHA", "share_of_core")); N["disha_cems"] = com(f("core", "DISHA", "cems_in_extent"))
    N["disha_drop_pct"] = pct(1 - f("core", "DISHA", "cems_in_extent") / f("core", "DISHA", "cems_in_core"))
    N["osu_v0_delivered"] = com(f("all", "OSU", "v0_flags_delivered")); N["osu_v1_delivered"] = com(f("all", "OSU", "v1_flags_delivered"))
    N["osu_v0_on_base"] = com(f("all", "OSU", "v0_flags_on_base")); N["osu_dropped"] = com(f("all", "OSU", "dropped_v0_to_v1")); N["osu_added"] = com(f("all", "OSU", "added_v0_to_v1"))
    N["field_n"] = com(f("all", "ChatMap", "n_points"))
    # own-footprint products: how the delivery maps onto the shared base (one rule, ADR-0030)
    for p in ("MS", "UNEP", "UH"):
        N[f"delivered_{p}"] = com(f("all", p, "delivered_footprints")); N[f"onbase_{p}"] = com(f("all", p, "base_buildings"))
        N[f"collapsed_{p}"] = com(f("all", p, "collapsed")); N[f"snapped_{p}"] = com(f("all", p, "mapped_by_snap"))
        N[f"orphans_{p}"] = com(f("all", p, "orphans")); N[f"median_iou_{p}"] = f2(f("all", p, "median_iou"))
    for p in ("IMPACT", "OSU", "LIST"):   # id-keyed deliveries: the delivered set IS a base-id set
        N[f"delivered_{p}"] = N[f"total_flags_{p}"]
    v = W("osu-versions", "points", 10)
    N["osu_common_cems"] = com(v.loc["v0 (common extent)", "n_ref"])


# ---------------------------------------------------------------- ratios quoted in the appendices
def _ratios():
    pts, pos = W("core", "points", 10), W("core", "points+possibly", 10)
    lift = (pos.P / pts.P.reindex(pos.index))
    N["possibly_lift_range"] = f"{lift.min():.1f}–{lift.max():.1f}×"
    N["possibly_ref_growth"] = f"{pos.n_ref.iloc[0] / N_CEMS_CORE:.1f}×"
    best_single = W("core", "points", 10).loc[PRODUCTS].P.max()
    margins = []
    for basis in ("destroyed", "dmg+destroyed", "incl_possibly"):
        t = W("core", f"labels-{basis}", 10)
        margins.append(t.loc["weighted fusion", "P"] / t.loc[PRODUCTS].P.max())
    N["fusion_margin_range"] = f"{min(margins):.1f}–{max(margins):.1f}×"
    # Which pairwise precision orderings change between the three reference bases? Computed, because the
    # prose once asserted "no comparison reverses" by hand and the one-rule frame made that false for UH.
    tabs = {b: W("core", f"labels-{b}", 10).P for b in ("destroyed", "dmg+destroyed", "incl_possibly")}
    preds = list(tabs["dmg+destroyed"].index)
    flipped = {(a, b) for i, a in enumerate(preds) for b in preds[i + 1:]
               if len({np.sign(t[a] - t[b]) for t in tabs.values()} - {0}) > 1}   # a tie at the CSV's rounding is not a reversal
    involved = sorted({x for pair in flipped for x in pair}, key=lambda x: -sum(x in pr for pr in flipped))
    if not flipped:
        N["basis_reversals"] = "No comparison reverses."
        N["basis_reversals_caption"] = "no comparison flips at any basis"
    else:
        culprit = involved[0]
        if all(culprit in pr for pr in flipped):
            rank = {b: list(tabs[b].loc[PRODUCTS].sort_values(ascending=False).index).index(culprit) + 1 for b in tabs}
            ordn = lambda k: f"{k}{'tsnrhtdd'[(k // 10 % 10 != 1) * (k % 10 < 4) * k % 10::4]}"
            N["basis_reversals"] = (f"Every reversal involves {culprit}: {ordn(rank['dmg+destroyed'])} among the single products under "
                                    f"the paper's reference, {ordn(rank['incl_possibly'])} once *possibly damaged* points count, the "
                                    f"signature of a destruction-biased product; no composite-versus-product comparison reverses.")
            N["basis_reversals_caption"] = f"only {culprit} changes rank; every composite stays above every product at every basis"
        else:
            N["basis_reversals"] = f"{len(flipped)} pairwise comparisons reverse, involving {', '.join(involved)}."
            N["basis_reversals_caption"] = f"{len(flipped)} pairwise orderings change ({', '.join(involved)})"
    w, e = W("strip-west", "points", 10), W("strip-east", "points", 10)
    N["strip_ms_ratio"] = f"{e.loc['MS', 'P'] / w.loc['MS', 'P']:.0f}×"
    F = W(lens="facts", radius=None, index=["region", "predictor"])
    N["osu_v0_saturated_pct"] = pct(F.loc[("all", "OSU"), "v0_share_probability_1"])


# ---------------------------------------------------------------- frozen: the Microsoft scene head-to-head (rq2g)
# rq2g scored Microsoft's two overlapping scenes on its own scene footprints by centroid distance
# (pre-ADR-0030 frame) against CEMS and the crowd. Its per-scene inputs (HASTE layers) lived in a
# session scratchpad that no longer exists, so these values cannot be regenerated. They are kept
# as declared constants with that provenance; the brief says so where it quotes them.
FROZEN_RQ2G = {
    "scene_ratio": "2.5", "scene_P_two": "0.245", "scene_P_one": "0.097", "scene_overlap_bld": "24,700",
    "scene_vantor_share": "4.9%", "scene_planet_share": "27.8%", "scene_vantor_conf": "7%", "scene_planet_conf": "14%",
    "scene_overruled_rejected": "68%", "scene_overruled_damaged": "845", "scene_both_rejected": "72%", "scene_vantor_only": "2,600",
}
N.update({f"frozen_{k}": v for k, v in FROZEN_RQ2G.items()})


# ---------------------------------------------------------------- crowd round 2 (rq7)
def _rq7():
    s = W("asd", "crowd-round2", 10).rename(columns={"strip_unmatched": "strip_unmatched_flags", "conf_r1": "unmatched_conf_share_r1", "conf_r2": "unmatched_conf_share_r2", "strip_share": "strip_share_of_covered_fps"})
    N["r2_MS_unmatched"] = com(s.loc["MS", "strip_unmatched_flags"])
    N["r2_MS_conf_r1"] = pct(s.loc["MS", "unmatched_conf_share_r1"], 1); N["r2_MS_conf_r2"] = pct(s.loc["MS", "unmatched_conf_share_r2"], 1)
    N["r2_MS_one_in"] = words(round(1 / s.loc["MS", ["unmatched_conf_share_r1", "unmatched_conf_share_r2"]].mean()))
    for p in ("MS", "UNEP", "IMPACT"):
        N[f"r2_padj_r1_{p}"] = f3(s.loc[p, "P_crowd_r1"]); N[f"r2_padj_r2_{p}"] = f3(s.loc[p, "P_crowd_r2swap"])
    N["r2_padj_maxdelta"] = f2(s.delta.abs().max())
    rep = W("strip", "crowd-round2", None).loc["MS"]
    N["r2_cells"] = com(rep["paired_task_cells"])
    N["r2_votes_per_cell"] = f"{rep['median_votes_per_task_r2']:.0f}"; N["r1_votes_per_cell"] = f"{rep['median_votes_per_task_r1']:.0f}"
    N["r2_latent_corr"] = f2(rep["latent_correlation"]); N["r2_raw_corr"] = f2(rep["pearson_raw"])
    N["r1_no_share_pct"] = pct(rep["cell_majority_no_share_r1"])


def _scope():
    """Damaged buildings flagged as each provider delivered them (Table 1): own footprints for MS/UNEP/UH,
    base-building ids for IMPACT/LIST, OSU's v0 delivery."""
    for p in ("MS", "UNEP", "UH"):
        N[f"native_{p}"] = N[f"delivered_{p}"]
    for p in ("IMPACT", "LIST"):
        N[f"native_{p}"] = N[f"total_flags_{p}"]
    N["native_OSU"] = N["osu_v0_delivered"]


for _fn in (_rq3, _rq2_rest, _ms_conf, _flags, _ratio, _frame, _facts, _ratios, _rq7, _scope):
    try:
        _fn()
    except FileNotFoundError as e:  # a not-yet-regenerated artefact: fail at render, loudly
        raise RuntimeError(f"brief_numbers: {e}") from e

if __name__ == "__main__":
    import sys
    keys = sys.argv[1:] or sorted(N)
    for k in keys:
        print(f"{k:32s} {N[k]}")
