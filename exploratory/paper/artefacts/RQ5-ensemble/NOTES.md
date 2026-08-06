# RQ5 — consensus ensemble — running notes

Script `scripts/rq5_ensemble.py` · `rq5_summary.csv` · `figs/rq5_pr_frontier_r10.png` ·
`figs/rq5_consensus_gaps.png`. Design + sign-off in `DESIGN.md`. First pass 2026-07-07.

Basis: construction on gold `building_flags` (Overture centroids; members MS / IMPACT v2 / OSU /
UH), scoring dual-anchor vs native CEMS builtUpP {2,3}, r=10 m (5/20 in CSV), universe =
CEMS latest extent ∩ member AOIs. UH AOI derived (H3 res-9 ∪ k=1 dilation over all UH footprints).
Quad-overlap region = 58.5 km² (≈ Caraballeda coastal strip + west Caracas edge), 1,455 CEMS pts,
56,052 buildings.

## Results (r=10 m; quad region unless noted)
| rule | flagged | P | R | F1 |
|---|---|---|---|---|
| MS (best single) | 9,050 | 0.082 | 0.476 | 0.140 |
| IMPACT | 22,954* | 0.033 | 0.457 | 0.061 |
| OSU | 31,259* | 0.037 | 0.681 | 0.070 |
| UH | 55,925* | 0.009 | 0.339 | 0.018 |
| IMPACT∧OSU (same-sensor) | 7,794 | 0.088 | 0.431 | 0.147 |
| MS∧IMPACT | 2,368 | 0.191 | 0.299 | 0.233 |
| IMPACT∧UH | 1,290 | 0.240 | 0.214 | 0.227 |
| **MS∧UH** | 1,014 | **0.373** | 0.261 | **0.307** |
| 1-of-4 (union) | 34,120 | 0.037 | **0.761** | 0.071 |
| 2-of-4 | 13,087 | 0.078 | 0.634 | 0.138 |
| **3-of-4** | 2,984 | 0.201 | **0.404** | **0.268** |
| 4-of-4 | 459 | **0.516** | 0.161 | 0.245 |

\* singles scored on their own full region (see CSV); pair rows here are the quad-region variants.

## Findings
1. **H2 CONFIRMED — consensus roughly doubles the map quality.** Best single F1 = 0.140 (MS);
   3-of-4 = 0.268, MS∧UH = 0.307. And the *precision* story is stronger: 3-of-4 gives 2.5× MS's
   precision at comparable recall (0.20/0.40 vs 0.08/0.48); 4-of-4 reaches **P = 0.52** — a
   majority of its 459 flags sit within 10 m of a CEMS damage point, vs 3–9 % for singles.
   Voting is doing real work, not just shrinking the set.
2. **H1 CONFIRMED — cross-sensor pairs dominate; same-sensor pair is nearly worthless.**
   On the identical universe, IMPACT∧OSU (both Sentinel-1) yields P = 0.088 — barely above MS
   alone — while every cross-sensor pair at least doubles it (MS∧IMPACT 0.19, IMPACT∧UH 0.24,
   MS∧UH 0.37). Exactly the RQ3b prediction: shared sensor physics ⇒ correlated FPs ⇒ AND can't
   remove them. Quantifies *why* naive "combine everything" is the wrong advice — modality
   diversity is the active ingredient.
3. **A terrible classifier is still a valuable voter.** UH alone is the worst product ever scored
   here (P = 0.009, 38× over-detection) yet MS∧UH is the best pair. Its errors are (a) plentiful
   but (b) nearly uncorrelated with MS's — textbook ensemble behaviour. Do NOT drop weak products
   from the consensus on single-product performance alone.
4. **The union (1-of-4) hits R = 0.76** — the "did anyone see it" layer; useful as the search
   frontier, hopeless as a map (P = 0.037).
5. **Consensus-as-CEMS-gaps: 27 % of 4-of-4 buildings (124 of 459) have NO CEMS point within
   20 m.** Four quasi-independent products agreeing on a building CEMS didn't enumerate is the
   strongest available evidence for CEMS under-enumeration (RQ2's two-sided attribution, used
   constructively). Map in `figs/rq5_consensus_gaps.png`; candidate field-validation set.

## Caveats
- Centroid-vs-footprint penalty: singles score lower here than RQ2's native-footprint numbers
  (MS R 0.48 vs ~0.6) — internally consistent across rules, but quote RQ2 for native single-product
  performance and RQ5 only for rule-vs-rule comparison.
- Quad region is small (58.5 km², Caraballeda-dominated) — same weighting caveat as RQ2/RQ3.
- UH provenance/modality unconfirmed (assumed optical AI) — H1's pair-typing for UH pairs is
  provisional; the IMPACT∧OSU vs MS∧IMPACT contrast alone carries H1 regardless.
- UH AOI is derived, not provider-supplied; res-9 dilation is generous at edges.
- Precision still CEMS-density-capped (RQ2) — the 0.52 of 4-of-4 is a floor on its true precision.

## Next
- Radius sensitivity table is in the CSV (r=5/20) — check rule ordering is stable (spot-check: it is).
- Grade-aware voting (weight destroyed > damaged) — deferred by design.
- Latency framing: consensus-as-of-day-X (needs the §6 timeline provider dates).
- Per-AOI split once more UH/CEMS overlap regions exist beyond Caraballeda.
