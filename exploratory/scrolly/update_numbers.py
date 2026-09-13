"""Re-point the scroll story's numbers from the paper artefact CSVs (ADR-0030).

Rewrites, in index.html: the BARDATA / RANKDATA / BOUNDS arrays and every prose number
that comes from an artefact. Every pattern must match exactly once or the script raises
and writes nothing. Run from the repo root after the artefact chain and the data exports.
"""
import re, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "exploratory/paper"))
from brief_numbers import N, rq5b, rq2r, PRODUCTS, LONG, csv, words, N_CEMS_CORE  # noqa: E402

html_path = pathlib.Path(__file__).parent / "index.html"
t = html_path.read_text()

def sub1(pattern, repl, flags=re.S):
    global t
    n = len(re.findall(pattern, t, flags))
    if n != 1:
        raise SystemExit(f"{n} matches for {pattern!r}")
    t = re.sub(pattern, lambda m: repl, t, count=1, flags=flags)

core = rq5b[10]
# --- agreement bars
labels = ["any 1 of 6", "2 or more", "3 or more", "4 or more", "5 or more", "all 6"]
bars = ",".join(f'["{lab}",{int(core.loc[f"{k}-of-6", "flagged"])},{100 * core.loc[f"{k}-of-6", "P_cems"]:.1f}]'
                for k, lab in zip(range(1, 7), labels))
sub1(r"const BARDATA = \[.*?\];", f"const BARDATA = [{bars}];")
k1, k6 = core.loc["1-of-6"], core.loc["6-of-6"]
sub1(r"from [\d,]+ flags at \d+% confirmed to [\d,]+\s+at \d+%",
     f"from {int(k1.flagged):,} flags at {100 * k1.P_cems:.0f}% confirmed to {int(k6.flagged):,}\n  at {100 * k6.P_cems:.0f}%")
# --- ranking bars (rq3h, res 8): best agreement rule + the six products
h = csv("RQ3-prioritization-error-structure/rq3h_agreement_ranking.csv")
h8 = h[h.res == 8].set_index("predictor")
votes = [p for p in h8.index if "-of-" in p]; best = h8.loc[votes, "rho"].idxmax()
singles = {"Microsoft": "Microsoft", "IMPACT v2": "IMPACT", "OSU": "OSU", "UH": "UH", "LIST": "LIST", "UNEP": "UNEP"}
rows = [f'["{best} agreement",{h8.loc[best, "rho"]:.3f},true]']
rows += [f'["{short}",{h8.loc[lab, "rho"]:.3f},false]' for lab, short in sorted(singles.items(), key=lambda kv: -h8.loc[kv[0], "rho"])]
sub1(r"const RANKDATA = \[.*?\];", "const RANKDATA = [" + ",".join(rows) + "];")
n07 = int((h8.loc[list(singles), "rho"] >= 0.7).sum())
sub1(r"\(\w+ of the six reach a Spearman ρ of 0\.7 or more", f"({words(n07)} of the six reach a Spearman ρ of 0.7 or more")
# --- precision bounds (rq2r): floor and upper bound, per cent, sorted by floor
b = rq2r.loc[PRODUCTS].sort_values("P_floor", ascending=False)
bounds = ",".join(f'["{LONG[p]}",{100 * r.P_floor:.1f},{100 * r.P_upper:.1f}]' for p, r in b.iterrows())
sub1(r"const BOUNDS = \[.*?\];", f"const BOUNDS = [{bounds}];")
sub1(r"no assessment does better than about one in \w+", f"no assessment does better than about one in {words(round(1 / rq2r.P_upper.max()))}")
prod = core.loc[PRODUCTS]
visits = prod.flagged / (rq5b[30].loc[PRODUCTS, "R_cems"] * N_CEMS_CORE)
sub1(r"roughly \d+ to \d+ site visits", f"roughly {visits.min():.0f} to {visits.max():.0f} site visits")
# --- arrivals: total flags per product on the shared base (rq2s)
tot = csv("RQ2-cems-footprint-points/rq2s_flag_totals.csv").set_index("product").total_flags
sub1(r"<strong>[\d,]+ buildings</strong> in the coastal strip", f"<strong>{tot['MS']:,} buildings</strong> in the coastal strip")
sub1(r"It flags <strong>[\d,]+ buildings</strong>\.", f"It flags <strong>{tot['IMPACT']:,} buildings</strong>.")
sub1(r"a different area of interest:\s+<strong>[\d,]+ buildings</strong>", f"a different area of interest:\n    <strong>{tot['OSU']:,} buildings</strong>")
sub1(r"debris tonnage \(<strong>[\d,]+</strong> buildings\)", f"debris tonnage (<strong>{tot['UNEP']:,}</strong> buildings)")
sub1(r"WFP, LIST and CERN\s+\(<strong>[\d,]+</strong>\)", f"WFP, LIST and CERN\n    (<strong>{tot['LIST']:,}</strong>)")
sub1(r"<strong>[\d,]+ flagged</strong>\. Two further", f"<strong>{tot['UH']:,} flagged</strong>. Two further")
sub1(r"answers from <strong>[\d,]+ to [\d,]+</strong>", f"answers from <strong>{tot.min():,} to {tot.max():,}</strong>")
sub1(r"a factor of \w+\.", f"a factor of {words(round(tot.max() / tot.min()))}.")
sub1(r"the six count anywhere from [\d,]+ to [\d,]+ damaged", f"the six count anywhere from {int(prod.flagged.min()):,} to {int(prod.flagged.max()):,} damaged")
# --- core labels and 4-of-6 count
meta = re.search(r'"expert": (\d+)', (pathlib.Path(__file__).parent / "data.js").read_text()).group(1)
sub1(r"The teal dots are the [\d,]+ buildings", f"The teal dots are the {int(meta):,} buildings")
sub1(r"more assessments agree \([\d,]+ of them\)", f"more assessments agree ({int(core.loc['4-of-6', 'flagged']):,} of them)")
html_path.write_text(t)
print("story numbers re-pointed:", {"bars": bars[:60], "best_rank": best, "visits": f"{visits.min():.0f}-{visits.max():.0f}", "tot_MS": int(tot['MS']), "expert": meta})
