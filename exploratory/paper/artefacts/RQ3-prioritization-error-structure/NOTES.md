# RQ3 — prioritization skill & error structure — running notes

Script `scripts/rq3_prioritization.py` · `rq3_prioritization_summary.csv` ·
`figs/rq3_rank_scatter_res8.png`. H3 res 8 (~0.74 km²) + res 7 (~5.2 km², triage-scale) within each
product's strict shared region. CEMS positive = {Damaged, Destroyed}.

## Results
| res | product | Spearman ρ | Kendall τ | top-20 | over-det median | "bias_rho" |
|---|---|---|---|---|---|---|
| 8 | Microsoft | 0.47 | 0.35 | 0.35 | 3.0× | −0.49 |
| 8 | IMPACT v2 | 0.30 | 0.23 | 0.25 | 6.3× | −0.28 |
| 8 | OSU | 0.51 | 0.41 | 0.45 | 19.1× | −0.36 |
| 7 | Microsoft | 0.57 | 0.42 | **0.85** | 6.1× | −0.81 |
| 7 | IMPACT v2 | 0.46 | 0.36 | 0.50 | 7.7× | −0.48 |
| 7 | OSU | 0.57 | 0.46 | **0.80** | 25.9× | −0.43 |

## Findings (the thesis gets QUALIFIED support)
1. **Prioritization survives at operational scale despite heavy over-detection.** At res 7
   (~5 km², a realistic triage unit) **Microsoft and OSU place ~80–85% of the top-20 worst-hit
   cells correctly** (top-20 concordance 0.85 / 0.80), with ρ ≈ 0.57 — even though OSU over-detects
   ~26× and RQ2 precision was 0.056. This is the core thesis: a noisy, low-precision product can
   still rank areas right. IMPACT v2 is the weak one (top-20 0.50, ρ 0.46).
2. **Skill is scale-dependent — the over-detection noise averages out.** Every product improves
   markedly from res 8 → res 7 (ρ and top-k both rise). Fine-grained ranking is noisy; coarse
   (district-level) ranking is usable. Directly supports "use these for *large-area* prioritization."
3. **OSU = maximal-recall, maximal-over-detection, still-ranks:** recall 0.86 (RQ2), over-det ~19–26×,
   yet best-or-tied rank skill. It floods flags but densely enough where damage is that the ranking holds.

## ⚠ METRIC FLAW — do not report `bias_rho` as-is [RESOLVED — superseded by RQ3b below]
`bias_rho` = Spearman(cems_count, product/cems ratio) is **not a clean bias test**: the ratio has
cems in the denominator, so it is *mechanically* inversely related to cems_count (small-denominator
effect) — a negative value is expected even under pure noise. It cannot distinguish structured bias
from noise. Replaced by the proper test in `scripts/rq3_error_structure.py` (RQ3b, 2026-07-07).

---

# RQ3b — error structure: the noise-vs-bias verdict (2026-07-07)

Script `scripts/rq3_error_structure.py` · `rq3_error_structure_summary.csv` ·
`figs/rq3_residual_maps_res8.png`. Universe = H3 cells with ≥1 base building in the strict shared
region (**zero-damage cells included** — the rank test's `cems>0 | pdmg>0` filter would hide FP
structure in undamaged areas). Poisson GLM `pdmg ~ log1p(cems)`, Pearson residuals, then
(a) Moran's I (h3 k=1 adjacency, row-standardised, 999 perms) and (b) OLS of residuals on z-scored
log-building-density, dist-to-coast (adm0 boundary), MMI (max of the two USGS ShakeMap events,
nearest-contour). **Two GLM specs**: `raw` (as originally proposed) and `exposure`
(offset = log base buildings). The exposure spec is the honest one: a cell with more buildings hosts
more flags at a constant per-building FP rate, so raw density dependence is mechanical, not bias.
That proved decisive — the raw spec shows huge "density bias" (b≈+3.7…+5.5, p≈0) that **vanishes
entirely under the exposure offset** (b ns for all three products).

## Results (res 8, exposure spec — headline)
| product | cells | disp | Moran's I (p) | b dens (p) | b coast (p) | b MMI (p) | R² |
|---|---|---|---|---|---|---|---|
| Microsoft | 131 | 57 | **0.60** (.001) | −0.16 (ns) | −0.81 (.046) | n/a (1 contour) | 0.01 |
| IMPACT v2 | 689 | 32 | **0.45** (.001) | +0.19 (ns) | −1.89 (<.001) | +0.43 (<.001) | 0.15 |
| OSU | 903 | 77 | **0.51** (.001) | −0.20 (ns) | −3.64 (<.001) | +1.82 (<.001) | 0.21 |

res 7 same pattern, stronger (I 0.52–0.66). Massive overdispersion throughout (Poisson disp 32–207)
— report as quasi-Poisson; coefficient signs/tests are what matter, not the Poisson likelihood.

## Verdict — NOT pure noise, but the structure is severity-aligned, which RESCUES prioritization
1. **The error is spatially structured.** Moran's I 0.45–0.60, p=.001 for every product/res/spec:
   per-building over-detection rates clump. The pure-noise hypothesis is dead.
2. **But the structure follows the severity gradient, not confounders.** Once exposure is
   controlled: density dependence gone (all ns); over-detection rises **toward the coast** and
   **with MMI** (IMPACT, OSU). Products over-call most *where the earthquake actually hit hardest*.
   Severity-aligned amplification preserves — arguably sharpens — area ranking; it is exactly the
   benign kind of structure consistent with RQ3a's finding that ranking survives 5–26×
   over-detection. The rank-corrupting kind (error following building stock, urban form) is what
   the exposure spec rules out.
3. **Microsoft's clump is a localized sub-region, not a gradient** (see residual map): a hard red
   cluster at the **west end of the Caraballeda strip** (~lon −67.05…−67.10) vs blue centre/east —
   covariates explain almost nothing (R²=0.01) yet I=0.60. This looks like the external group's
   "high FP in a specific sub-region" report (§4.5 named investigation) found independently.
   Localize it against imagery/terrain next.
4. **Attribution stays two-sided** (same as RQ2): "over-detection" concentrated in worst-hit coastal
   cells could equally be CEMS builtUpP incompleteness peaking where damage (and analyst workload)
   peaked. The test detects *structure*; it cannot assign it to product FP vs CEMS FN. Say so in
   the paper — it does not weaken the prioritization conclusion, which holds either way.

## Caveats
- MMI covariate unavailable for Microsoft (Caraballeda sits within a single ShakeMap contour) —
  coast + Moran carry that test. MMI is nearest-contour (±half interval), not the continuous grid.
- dist-to-coast = distance to adm0 boundary (≡ coast for these AOIs, but inland AOIs would need a
  real coastline layer).
- Covariate R² ≤ 0.27 and Moran's I stays high in all specs → most of the clumping is NOT explained
  by the three covariates (candidates: SAR incidence/swath geometry, terrain slope, urban fabric).
  Fine for the verdict (we only needed noise-vs-bias + which kind); flag as residual unknown.
- Base stock from gold `building_flags` (id/lon/lat only — no damage labels read); RQ0-clean.

## Caveats / next
- top-10 concordance is unstable (small k + ties: MS res8 top10=0.10 but top20=0.35). Lead with
  top-20/top-50 and res 7.
- Caraballeda dominates CEMS points → results are Caraballeda-weighted; per-AOI split needed.
- ~~Proper error-structure test (residual Moran's I + covariates)~~ **done — RQ3b above.**
- Localize the Microsoft west-Caraballeda over-detection cluster (RQ3b finding 3) against
  imagery/terrain — feeds the §4.5 named investigation directly.
- Add admin-unit (adm2/adm3) ranking alongside H3 for operational framing.
- Add IMPACT v1 for the v1↔v2 contrast.

---

# RQ3b addendum — Moran's I per CEMS area (2026-07-08)

Script `scripts/rq3b_per_area_moran.py` · `rq3b_per_area_moran.csv`. Same exposure-spec GLM +
permutation Moran's I, split by CEMS aoi_name + pooled; members incl. UH; basis = gold
building_flags (RQ5/RQ2c construction basis, not the native-footprint basis of the original run).

| area (n CEMS pts) | IMPACT | MS | OSU | UH |
|---|---|---|---|---|
| Caraballeda (1,455) | 0.30*** | **0.60***\* | 0.39*** | 0.53*** |
| Caracas (3) | 0.28*** | — | 0.30*** | 0.37*** |
| Moron (26) | 0.00 ns | — | (sliver) | 0.09 ns |
| San Felipe (14) | 0.05 ns | — | 0.40*** | — |
| Santa Cruz (3) | 0.05 ns | — | 0.04 ns | 0.33*** |
| ALL pooled | 0.45 | 0.60 | 0.51 | 0.40 |
\*\*\* p=.001 (999 perms)

## Findings
1. **Within-area clustering is real, not a pooling artifact** — significant in every
   damage-bearing area for every product present. BUT pooled I > within-area I for IMPACT
   (0.45 vs 0.30) and OSU (0.51 vs 0.39): part of the pooled signal is BETWEEN-area mean
   shifts (swath/regional effects). Two scales of structure; report both.
2. **Where the SAR products go quiet, their errors are clean noise:** IMPACT & OSU in Santa
   Cruz (flag ~1%, I ≈ 0.05 ns) — sparse salt-and-pepper FPs. The desirable behaviour.
3. **UH's inland over-flagging is CLUMPED** (Santa Cruz I=0.33***, 27.5% flags; Caracas
   I=0.37***): systematic, spatially coherent model failure (imagery tiles / neighbourhood
   fabric?), not diffuse noise. Strengthens the RQ2c indictment.
4. **OSU San Felipe oddity:** only 1.1% flagged yet I=0.40*** — its few FPs there cluster
   somewhere specific (port/industrial Puerto Cabello?). Candidate mini-investigation.
5. MS Caraballeda I=0.60 = the west-cluster again (basis change didn't move it: 0.604 native).
