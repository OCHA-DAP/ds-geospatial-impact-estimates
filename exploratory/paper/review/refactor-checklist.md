# Paper pipeline refactor — checklist (branch paper-polygon-frame, 2026-09-14)

Goal: the brief reads every number from one results table produced by a Snakemake DAG;
shared definitions live in one library; every step below is verified before the next.

Verification used throughout: `N_before == N_after` for the brief's key dictionary
(`brief_numbers.py`), so the prose never changes; per-script CSVs identical to git HEAD after a
script migration; `snakemake -n` shows nothing stale after a full build.

## A. DAG over the existing scripts
- [x] A1 Snakefile parses; `snakemake -n` lists the expected rules; no cycles
- [x] A2 `snakemake --touch` on the current (verified) tree so mtimes match git state
- [x] A3 one light rule rerun end to end (rq2s) reproduces its CSV byte-for-byte

## V. Vertical slice (prove the pattern before extending it)
- [x] V1 library slice: core_region(), cems(classes), flags(), score(flags, ref, r), votes(); pytest on synthetic geometry
- [x] V2 pipeline/scorecards.py computes core/points/10 for 6 products + 6 pairs + 6 rules → rows
- [x] V3 rows equal the oracle (results.csv from rq5b) to the CSV's rounding; Snakemake rule runs it
- [x] V4 decision point: pattern proven → extend; else stop and rethink

## B. One results table (the oracle)
- [x] B1 snapshot `N` from today's brief_numbers (baseline)
- [x] B2 consolidate.py: rq5b (r10/20/30) + rq2i → results.csv; brief_numbers core/asd keys read results.csv; keys equal baseline
- [x] B3 add rq2q, rq2r, rq2_chatmap, rq2k, rq2s; keys equal
- [x] B4 add rq3f (3 scopes), rq3h, rq3g, rq3b, rq3d; keys equal
- [x] B5 add rq8, rq8b, rq9, rq7, rq0, rq2l/o/h/p, density null, ms-confidence, frame deltas; keys equal
- [x] B6 brief_numbers reads only results.csv (+ formatting)
- [x] B6b the three table chunks in the qmd (dial, CI core, CI models) read results.csv too
- [x] B7 `snakemake results brief` renders; rendered text identical to the pre-refactor render

## C. Guards
- [x] C1 audit_brief_numbers.py written and wired as a rule (65 literals remain until section E)
- [x] C2 diff_results.py --base <ref>: builds results at the ref from its CSVs and reports changed values with the brief keys affected; run vs origin/v1
- [x] C3 pytest: results invariants (bounds monotone, floor ≤ crowd ≤ upper, k-of-6 P↑ R↓, rq5b=rq2q=rq2r=rq9 on shared cells, coverage ≤ 1, every brief key present)

## D. Library consolidation → compact modules (oracle-verified; heavy chain frozen)
- [x] D1 pipeline/paperlib.py holds the definitions (frame, matching, crowd credit, regions, predictors); 5 synthetic-geometry tests
- [x] D2–D7 pipeline/scorecards.py (rq5b, rq2q, rq2r, rq2i, rq2s, rq2k, rq2l, rq2o, rq2_chatmap) and pipeline/ranking.py (rq3f ×3, rq3h): 1,257 oracle values identical, 17 differences explained (two old definitional deviations), 0 unexplained
- [x] D8 `snakemake -n` clean; full `snakemake all`; commit

## E. Remaining hand-typed numbers
- [x] E1 region_facts artefact (core area/buildings, CEMS per AOI and grade, LIST shares, centroid spacing, H3 areas) → results.csv → keys
- [x] E2 rq0 cloud share and OSU version totals written to CSV → keys
- [ ] E3 parameters as named constants shared by scripts and prose (radii, cell sizes, CI settings still allowlisted literals)
- [x] E4 frozen scene head-to-head numbers declared as constants with provenance
- [x] E5 audit passes with an allowlist of dates/units only

## F. Wrap-up
- [x] F1 ADR-0032 (pipeline + results table); runner shells removed; README updated
- [x] F2 diff report vs origin/v1 attached to PR #116; Tristan checklist statuses filled

## G. Promotion (2026-09-14)
- [x] G1 lib/, frozen/ + MANIFEST, pipeline/figs, results at paper root; `all` reaches nothing under artefacts/
- [x] G2 verification build green (five relaunches: fig output paths, legacy dir, contextily, per-AOI figure still read artefacts/); render text identical to the pre-promotion render (870 text nodes, 0 differences); `-n` clean
- [x] G3 one footprint rule (IoU 1:1) applied to MS/UNEP/UH; diff 9/9 vs 0c9cc12, Table 1 delivered vs on-base
- [x] G4 diff vs live restated for the one-rule mapping (UNEP/UH may move ≤ 2%; ranking ρ ≤ 0.02 for the three re-mapped products): 12/12; `review/diff_vs_live_v1.md` refreshed
- [x] G5 oracle re-run under the current conventions (15 archived scripts, 00:28–01:30 on 2026-09-15; the archive's gie_paper shim had imported itself and was fixed first). 878 rows: 860 identical, 18 explained (rq2i's fp_crowd_damaged denominator; rq2i/rq5b representative point taken in lon/lat, one building for 5-of-6), 0 unexplained. rq2r, rq2_chatmap and the three rq3f null rankings re-ran byte-identical to the pipeline exports
- [ ] G6 push + PR #116 body (promotion, one-rule mapping, oracle rule)

## H. Things that bit (for the next person)
- `/tmp/gie_base_local` is wiped by macOS after three idle days; every buildings() call then fails loud. Rebuild command in README.
- Snakemake does not rebuild a missing *input* of an up-to-date output (`--summary` shows "missing / no update"); target the file itself.
- Never `--unlock` without `pgrep -f "snakemake -s"`.
- Fig scripts built by hand outside Snakemake have no provenance; `--forcerun` them once under the DAG.
- Figure TITLES are not covered by the number audit. The before/after page (2026-09-15, `_audit/figs_before_after.html`, regenerated from the frozen-v3 tag in a scratch worktree) found three: fig-frontier's fixed recall axis clipped 1-of-6 and 2-of-6; fig-bounds' hand-typed lift range (2.2–3.6×) was stale; fig-basis' "no comparison flips" was false under both frames (UH's rank changes). All three are now computed from the data; the brief's matching prose quotes `basis_reversals`.
- `frozen/MANIFEST.csv` used to stamp the vendoring HEAD as `producing_commit`; it now records the last commit that changed each archive file, so a file that was never re-run (rq7_west_cluster_join.csv, from 2fb074b) shows its real provenance.
