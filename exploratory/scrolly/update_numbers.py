"""Re-point the scroll story's numbers from the paper artefact CSVs (ADR-0030).

Rewrites, in index.html: the BARDATA / RANKDATA / BOUNDS arrays and every prose number
that comes from an artefact. Every pattern must match exactly once or the script raises
and writes nothing. Run from the repo root after the artefact chain and the data exports.
"""
import re, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "exploratory/paper"))
from brief_numbers import N, rq5b, rq2r, PRODUCTS, LONG, L, W, words, N_CEMS_CORE  # noqa: E402

html_path = pathlib.Path(__file__).parent / "index.html"
t = ORIGINAL = html_path.read_text()
CHECK = "--check" in sys.argv[1:]          # report staleness, write nothing (used by audit_numbers.py and the DAG)
OWNED: set = set()                          # every numeral this script wrote; audit_numbers.py treats any other as hand-typed
NUM = re.compile(r"\d(?:[\d,]*\d)?(?:\.\d+)?")

def sub1(pattern, repl, flags=re.S):
    global t
    n = len(re.findall(pattern, t, flags))
    if n != 1:
        raise SystemExit(f"{n} matches for {pattern!r}")
    def _r(m):
        out = repl(m) if callable(repl) else repl
        OWNED.update(NUM.findall(out))
        return out
    t = re.sub(pattern, _r, t, count=1, flags=flags)

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
h8 = W("core", "cells-agreement", 8)
votes = [p for p in h8.index if "-of-" in p]; best = h8.loc[votes, "rho"].idxmax()
singles = {"Microsoft": "Microsoft", "IMPACT v2": "IMPACT", "OSU": "OSU", "UH": "UH", "LIST": "LIST", "UNEP": "UNEP"}
rows = [f'["{best} agreement",{h8.loc[best, "rho"]:.3f},true]']
rows += [f'["{short}",{h8.loc[lab, "rho"]:.3f},false]' for lab, short in sorted(singles.items(), key=lambda kv: -h8.loc[kv[0], "rho"])]
sub1(r"const RANKDATA = \[.*?\];", "const RANKDATA = [" + ",".join(rows) + "];")
n07 = int((h8.loc[list(singles), "rho"] >= 0.7).sum())
sub1(r"\(\w+ of the six agree closely with", f"({words(n07)} of the six agree closely with")
# --- precision bounds (rq2r): floor and upper bound, per cent, sorted by floor
b = rq2r.loc[PRODUCTS].sort_values("P_floor", ascending=False)
bounds = ",".join(f'["{LONG[p]}",{100 * r.P_floor:.1f},{100 * r.P_upper:.1f}]' for p, r in b.iterrows())
sub1(r"const BOUNDS = \[.*?\];", f"const BOUNDS = [{bounds}];")
sub1(r"no assessment does better than about one in \w+", f"no assessment does better than about one in {words(round(1 / rq2r.P_upper.max()))}")
prod = core.loc[PRODUCTS]
visits = prod.flagged / (rq5b[30].loc[PRODUCTS, "R_cems"] * N_CEMS_CORE)
sub1(r"roughly \d+ to \d+ site visits", f"roughly {visits.min():.0f} to {visits.max():.0f} site visits")
# --- arrivals: damaged buildings flagged AS DELIVERED (the brief's Table 1 convention: the provider's own
# footprints for Microsoft/UH/UNEP, base ids for IMPACT/LIST, OSU v0). Core-region sentences stay on the shared base.
import pandas as pd
tot = pd.Series({p: int(N[f"native_{p}"].replace(",", "")) for p in PRODUCTS})
# the timeline's ARRIVALS array carried hand-typed counts until 2026-09-15 (Microsoft still read 9,635)
for label, p in (("Microsoft AI4G", "MS"), ("IMPACT", "IMPACT"), ("OSU / NASA", "OSU"), ("UNEP/OCHA", "UNEP"), ("WFP/LIST/CERN", "LIST"), ("UH SAIL", "UH")):
    sub1(r'(\{ name:"' + re.escape(label) + r'",[^\n]*? n:)\d+', lambda m, v=tot[p]: f"{m.group(1)}{v}")
sub1(r"<strong>[\d,]+ buildings</strong> in the coastal strip", f"<strong>{tot['MS']:,} buildings</strong> in the coastal strip")
sub1(r"It flags <strong>[\d,]+ buildings</strong>\.", f"It flags <strong>{tot['IMPACT']:,} buildings</strong>.")
sub1(r"a different area of interest:\s+<strong>[\d,]+ buildings</strong>", f"a different area of interest:\n    <strong>{tot['OSU']:,} buildings</strong>")
sub1(r"debris tonnage \(<strong>[\d,]+</strong> buildings\)", f"debris tonnage (<strong>{tot['UNEP']:,}</strong> buildings)")
sub1(r"WFP, LIST and CERN\s+\(<strong>[\d,]+</strong>\)", f"WFP, LIST and CERN\n    (<strong>{tot['LIST']:,}</strong>)")
sub1(r"<strong>[\d,]+ buildings flagged</strong>\. Two further", f"<strong>{tot['UH']:,} buildings flagged</strong>. Two further")
sub1(r"answers from <strong>[\d,]+ to [\d,]+</strong>", f"answers from <strong>{tot.min():,} to {tot.max():,}</strong>")
sub1(r"a factor of \w+\.", f"a factor of {words(round(tot.max() / tot.min()))}.")
sub1(r"the six count anywhere from [\d,]+ to [\d,]+ damaged", f"the six count anywhere from {int(prod.flagged.min()):,} to {int(prod.flagged.max()):,} damaged")
# --- the shortlist test (rq3h, res 8): the voting rule with the best top-20 overlap vs the best single product
WORDS_K = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
best_top = h8.loc[votes, "top20"].idxmax(); best_single = h8.loc[list(singles), "top20"].idxmax()
sub1(r"\w+-of-six agreement finds \d+ of the true worst 20; the best single assessment finds\s+\d+\.",
     f"{WORDS_K[int(best_top[0])]}-of-six agreement finds {round(20 * h8.loc[best_top, 'top20'])} of the true worst 20; the best single assessment finds\n  {round(20 * h8.loc[best_single, 'top20'])}.")
# --- the core region and the cell size (facts): three mentions of the area, one of the building count, two of the cell
sub1(r"where all overlap \(~[\d.]+ km²\)", f"where all overlap (~{N['core_area_km2']} km²)")
sub1(r"overlap: [\d.]+ km² and [\d,]+ shared", f"overlap: {N['core_area_km2']} km² and {N['core_n_buildings']} shared")
sub1(r"comparison area is only\s+[\d.]+ km²", f"comparison area is only\n    {N['core_area_km2']} km²")
sub1(r"damage per cell \(~[\d.]+ km²\)", f"damage per cell (~{N['h3_res8_km2_1']} km²)")
sub1(r"neighbourhood cells of about [\d.]+ km² each", f"neighbourhood cells of about {N['h3_res8_km2_1']} km² each")
# --- core labels and 4-of-6 count
meta = re.search(r'"expert": (\d+)', (pathlib.Path(__file__).parent / "data.js").read_text()).group(1)
sub1(r"The teal dots are the [\d,]+ buildings", f"The teal dots are the {int(meta):,} buildings")
sub1(r"more assessments agree \([\d,]+ of them\)", f"more assessments agree ({int(core.loc['4-of-6', 'flagged']):,} of them)")
(pathlib.Path(__file__).parent / ".numbers_owned.json").write_text(__import__("json").dumps(sorted(OWNED)))
if CHECK:
    if t != ORIGINAL:
        changed = [l for l in __import__("difflib").unified_diff(ORIGINAL.splitlines(), t.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
        raise SystemExit("update_numbers --check: index.html is STALE against results.csv:\n" + "\n".join(c[:160] for c in changed[:20]))
    print("update_numbers --check: index.html is current"); sys.exit(0)
if t != ORIGINAL:
    html_path.write_text(t)     # write only on change, so the DAG does not see a touched input every run
print("story numbers re-pointed:", {"bars": bars[:60], "best_rank": best, "visits": f"{visits.min():.0f}-{visits.max():.0f}", "tot_MS": int(tot['MS']), "expert": meta})
