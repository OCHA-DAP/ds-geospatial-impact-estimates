# RQ6 — DIY Sentinel-1 amplitude CCD — running notes

Scripts `scripts/rq6_gee_export.py` (GEE, 34 tiles, all CEMS extents) + `scripts/rq6_score.py`.
Outputs: `rq6_curve.csv`, `rq6_objects_grid.csv`, `rq6_holdout_result.txt`,
`rq6_negative_controls.csv`, `figs/rq6_curve_vs_frontier.png`. First pass 2026-07-08.

Method as built: GEE S1 GRD (amplitude only — no coherence in GEE), per orbit
z = (dB_post − mean(dB_pre,30 scenes)) / std(dB_pre) floored 0.5 dB, max |z| over VV/VH and
orbits, 10 m, post = 2026-06-25…07-08. Building-level score = z sampled at Overture centroids
(gold building_flags), dual-anchor r=10 m vs CEMS {2,3}, Caraballeda area (1,455 pts — same
region scale as the RQ5 quad frontier).

## Results
1. **Threshold curve ties the best single product, beats the SAR singles per-building.**
   Max F1 = 0.137 @ z≈2.75–3.25 (MS = 0.140). At UH's recall (0.34) DIY precision is ~7× UH's
   (0.065 vs 0.009); at IMPACT's recall (0.46) DIY ≈ 0.044 vs 0.033. A weekend amplitude
   pipeline ≈ the per-building skill of the shipped products.
2. **PREDICTION A CONFIRMED — the curve cannot reach the cross-modal ensemble.** At R=0.40 the
   curve gives P≈0.06 vs 3-of-4's 0.201 (3–4× above); at R=0.16, P≈0.15 vs 4-of-4's 0.516. The
   curve visibly saturates (P=0.34 at R=0.03). Threshold tuning moves along the modality's
   curve; it does not step over the correlated-FP floor. Consensus across modalities does.
3. **Object-level clustering DID NOT help (as implemented).** Best tune config degenerated to
   s=1 (no clustering); held-out east F1 = 0.055 ≪ building-level 0.137. Min-size filters
   destroyed recall faster than they bought precision (t=3, s=20: P=0.067, R≈0.001), and
   component centroids often sit off-building. Fair caveat: this scored component *centroids*;
   a footprint-aggregation rule (flag building iff ≥x% of its pixels exceed z) is the better
   object formulation and remains untested. Also note tune→holdout P drop (0.091→0.052):
   west/east heterogeneity is real.
4. **Negative controls: PARTIAL FAIL — Santa Cruz.** Flag rates (share of buildings):
   z≥2.5: Caraballeda 6.2%, Caracas 3.5%, **Santa Cruz 8.0%** (exceeds Caraballeda!);
   z≥4: 1.0 / 0.2 / 0.8. Caracas contrast is OK (~2–5×); Santa Cruz is not — likely
   agricultural/land-use amplitude change the 30-scene std baseline under-penalizes.
   Notably IMPACT/OSU (coherence) flag only 1.2/0.9% in Santa Cruz (RQ2c): **coherence
   handles vegetated/agricultural FP better than amplitude**; our DIY inherits UH-like
   inland behaviour, milder.

## Interpretation for the paper
The DIY experiment sharpens the RQ5 conclusion rather than overturning it: a carefully
normalized single-sensor product can match the best single product's operating curve, but no
point on that curve approaches the cross-modal consensus. "Tune harder" is not a substitute
for "combine modalities". The Santa Cruz result adds a modality note: coherence > amplitude
for suppressing rural/agricultural false positives.

## Caveats / next
- Amplitude ≠ coherence: GEE constraint. A HyP3 coherence rerun of the same design is the
  right apples-to-apples DIY and could shift result 1 (not the frontier conclusion, per
  IMPACT∧OSU's plateau).
- Footprint-fraction object rule untested (see 3).
- Pre-stack = 30 most recent scenes (GEE memory limit); a full-year seasonal baseline might
  fix some Santa Cruz FP.
- Same centroid-scoring + CEMS-density-cap caveats as RQ5.
