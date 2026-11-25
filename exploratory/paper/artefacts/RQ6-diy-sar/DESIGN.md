# RQ6 — DIY Sentinel-1 CCD: can smarter processing + threshold sweep beat the products (or the ensemble)?

Status: **PROPOSED — design agreed 2026-07-07 (user + assistant), data work not started.**

## Question & competing predictions (stated up front so this is a real test)

The provider SAR products are fixed operating points on unknown curves. We build our own
Sentinel-1 coherence-change detection with (a) smarter normalization, (b) a full threshold
sweep, and (c) object-level post-processing, and ask: **does any point on the DIY curve reach
the cross-modal ensemble's operating points (e.g. 3-of-4: P=0.20 @ R=0.40; MS∧UH: P=0.37 @
R=0.26)?**

- **Prediction A (assistant):** no — the correlated-FP floor seen in IMPACT∧OSU (P=0.088 on the
  identical universe) reflects modality physics (vegetation, layover, unstable scatterers produce
  *strong* coherence change that survives any threshold); the DIY curve saturates near P≈0.1 at
  useful recall.
- **Prediction B (user):** yes, or at least materially better than IMPACT/OSU — the rapid
  products are likely under-processed (single pre-event pair, no stability normalization, no
  object-level cleaning), so there is headroom a careful pipeline recovers.

Either outcome is a paper result: A ⇒ "combine modalities, don't tune harder"; B ⇒ "the fast-SAR
story improves with cheap discipline" (and the better member lifts the RQ5 ensemble too).

## Method sketch

1. **Data:** Sentinel-1 SLC pairs via ASF (or ASF HyP3 on-demand InSAR/coherence to skip local
   SNAP/ISCE processing). Pre-event stack of ≥3–4 pairs for a per-pixel coherence baseline
   (mean, std) — not a single pre pair; co-/post-event pair(s) matching the products' acquisition
   dates (latency framing: what was *achievable* when).
2. **Detection statistic ("smarter processing"):** per-pixel coherence z-score vs the pre-event
   baseline (drop normalized by that pixel's own historical stability), NOT a raw coherence
   difference with one global threshold. Pixels with chronically unstable coherence (vegetation,
   water, agriculture) are down-weighted or masked by the baseline itself.
3. **Threshold sweep:** the full curve, not a point.
4. **Object-level post-processing sweep (user's suggestion):** connected-component clustering of
   super-threshold pixels → one detection per damage *object*; minimum-cluster-size filter;
   morphological opening; building-footprint aggregation (footprint flagged iff ≥x% of its pixels
   detect). Each is a hyperparameter.
5. **Scoring:** identical dual-anchor harness (RQ0), r=10 m, vs CEMS {2,3}; overlay the DIY curve
   on the RQ5 frontier figure.

## Guardrails

- **Overfitting/leakage:** the decision space (threshold × cluster size × morphology × footprint
  rule × mask) is easily large enough to overfit 1,455 CEMS points. **Spatial holdout is
  mandatory:** tune on one part of the CEMS coverage (e.g. west Caraballeda strip), report on the
  held-out remainder (east strip + Moron), never iterate on the test split. State the split in
  every figure caption.
- **Negative-control areas:** the CEMS Caracas & Santa Cruz extents (analysed, ~3 damage points
  each) are the FP testbed — a good configuration must go *quiet* there (flag rate ≪ Caraballeda,
  the RQ2c contrast). Tune for contrast, not just Caraballeda hits.
- **Recall cost of object filtering:** min-cluster-size erases isolated single-building damage by
  construction — report grade-stratified recall (does it preferentially lose CEMS "Damaged" vs
  "Destroyed"?).
- **Scope discipline:** the paper's headline evaluation stays about the products responders
  actually received; RQ6 is the explanatory/hypothetical layer ("what was achievable"), one
  subsection, not a re-centering of the paper.

## Open items before compute

1. Acquisition inventory: which S1 orbits/dates cover the CEMS extents pre/post event (check vs
   IMPACT's stated acquisitions); ascending vs descending, or both.
2. HyP3 vs local processing decision (HyP3 = fast, standardized, coherence GeoTIFFs; local =
   full control over multilooking/filtering).
3. Confirm CEMS Caracas/Santa Cruz monitoring completeness (standing flag #1) — the negative
   controls depend on it.
