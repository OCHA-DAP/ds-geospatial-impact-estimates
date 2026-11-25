# RQ1 — CEMS coarse blocks — running notes

> **SCOPE CORRECTION (2026-07-05):** The primary performance analysis is **sources vs CEMS damage
> POINTS** (→ RQ2), not sources vs coarse blocks. The coarse blocks are a *secondary* reference; the
> requested coarse-block analysis is **CEMS coarse blocks vs CEMS damage points** (an internal
> early-vs-refined check — see `scripts/rq1b_coarse_vs_points.py`). The sources-vs-coarse-blocks work
> below is **kept as supplementary** (still a valid cross-check), not the headline.

## [SUPPLEMENTARY] sources vs CEMS coarse blocks — running notes

Script: `scripts/rq1_coarse_blocks.py` · summary: `rq1_coarse_summary.csv` · fig:
`figs/rq1_coarse_concordance.png`. Basis: dual-anchor design (RQ0), silver/bronze snapshots.

## Method (v1)
CEMS coarse blocks = 355 damaged-area polygons (builtUpA), AOIs 2/6/8/12, all monitoring_number 0
(initial products). Coarse coverage = union of the 15 initial (monitoring 0) CEMS analysed-extent
polygons for those AOIs — **all 355 blocks fall inside it** (sanity ✓). Per product, region =
coarse_coverage ∩ product_AOI, metric CRS 32619. Damaged buildings = representative points.

Metrics: `in_block_rate` (dmg buildings inside a block / dmg in region); **`lift_over_chance`**
(= in_block_rate / block-area-fraction — the honest metric); `block_recall` (blocks with ≥1 dmg
building); `grade_spearman` (block ordinal grade vs product dmg count per block).

## First run (2026-07-05)
| product | region blocks | dmg in region | in_block_rate | block_area_frac | **lift** | block_recall | grade ρ (p) |
|---|---|---|---|---|---|---|---|
| Microsoft | 166 | 7,868 | 0.305 | 0.091 | **3.36** | **0.940** | 0.079 (0.31, ns) |
| IMPACT v2 | 315 | 14,056 | 0.308 | 0.044 | **6.96** | 0.565 | 0.492 (1e-20) |
| OSU | 265 | 27,154 | 0.300 | 0.028 | **10.63** | 0.694 | 0.517 (2e-19) |

## Findings
1. **`in_block_rate` alone is a trap** — ~0.30 for all three, but only because block-area-fraction
   differs (MS 0.091 vs OSU 0.028). The **lift over chance (3.4–10.6×)** is the real result: all
   three concentrate damage inside CEMS coarse blocks *far* above random. They agree with CEMS on
   *where* damage is.
2. **SAR products track the CEMS severity gradient; Microsoft does not.** IMPACT v2 & OSU block
   grade↔dmg-count ρ ≈ 0.5 (highly sig); MS ρ ≈ 0.08 (ns). Early support for SAR carrying a
   severity signal vs MS's flatter binary optical call. (Caveat: MS region = Caraballeda only.)
3. **Microsoft has very high block_recall (0.94) on its region** — finds damage in nearly every
   Caraballeda block — but its AOI only overlaps 166 of the 355 blocks (Caraballeda); it never
   covers Moron/San Felipe. IMPACT/OSU span more blocks but hit fewer (0.57 / 0.69).

## CAVEATS / must-fix before this is paper-grade
- **Lift is NOT cross-product comparable here** — each product covers a different region (MS tiny
  dense Caraballeda; IMPACT/OSU huge sparse swaths), and block-area-fraction (hence lift) depends
  on region. Next pass: restrict all products to a **common region** (intersection of the three
  AOIs) AND/OR score **per-AOI**, so lift/recall are comparable.
- MS grade concordance is over Caraballeda blocks only (limited grade range) — not comparable to
  IMPACT/OSU which span 4 AOIs. Report per-AOI.
- Representative-point-in-block is a reasonable areal test; sensitivity to using footprint-overlap
  instead is untested.
- Coarse blocks are the EARLY/coarse estimate and may under-delineate true damage — so damage
  "outside blocks" is not necessarily FP. Interpret in_block concentration, not raw precision.

## Next
1. Common-region + per-AOI re-scoring (makes lift/recall comparable). 
2. Bring in IMPACT v1 (needs local re-materialisation) once RQ2 helper exists.
3. Then RQ2 (points, dual-anchor P/R/F1).
