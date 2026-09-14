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
- [ ] V4 decision point: pattern proven → extend; else stop and rethink

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
- [ ] C1 audit_brief_numbers.py: numeric literals in prose vs allowlist; wired as a rule; passes
- [ ] C2 diff_results.py --base <ref>: builds results at the ref from its CSVs and reports changed values with the brief keys affected; run vs origin/v1
- [ ] C3 pytest: results invariants (bounds monotone, floor ≤ crowd ≤ upper, k-of-6 P↑ R↓, rq5b=rq2q=rq2r=rq9 on shared cells, coverage ≤ 1, every brief key present)

## D. Library consolidation (main-section scripts only; heavy chain frozen)
- [ ] D1 gie_paper gains: core_region(), product_aois(), uh_aoi(), cems(classes), field_points(), crowd_tasks(), crowd_verdicts(gdf), score(flags, ref, r), crowd_credit(...), cells(gdf, res); pytest on synthetic geometry
- [ ] D2 migrate rq5b → CSV identical to HEAD
- [ ] D3 migrate rq2q → identical
- [ ] D4 migrate rq2i → identical
- [ ] D5 migrate rq2r, decoupled from the rq8 parquet → identical
- [ ] D6 migrate rq2_chatmap, rq2s → identical
- [ ] D7 migrate rq3f (3 scopes), rq3h with fusion optional → identical
- [ ] D8 `snakemake -n` clean; full `snakemake all`; commit

## E. Remaining hand-typed numbers
- [ ] E1 region_facts artefact (core area/buildings, CEMS per AOI and grade, LIST shares, centroid spacing, H3 areas) → results.csv → keys
- [ ] E2 rq0 cloud share and OSU version totals written to CSV → keys
- [ ] E3 parameters as named constants shared by scripts and prose
- [ ] E4 frozen scene head-to-head numbers declared as constants with provenance
- [ ] E5 audit passes with an allowlist of dates/units only

## F. Wrap-up
- [ ] F1 ADR-0032 (pipeline + results table); runner shells removed; README updated
- [ ] F2 diff report vs origin/v1 attached to PR #116; Tristan checklist statuses filled
