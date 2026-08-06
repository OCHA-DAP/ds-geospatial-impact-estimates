# RQ8 — learned fusion (stacking): can a meta-model beat the k-of-6 dial?

Status: agreed 2026-07-15 (user proposal). One tight pass; earns a paper section ONLY if it
beats the dial on held-out zones, else becomes one discussion sentence.

- **Features** (per Overture building, core region): six flags; product classes where they
  exist (uh/sar/osu/list/cems? — cems_class EXCLUDED, it is the label side); MS continuous
  damage_pct + num_observations (nearest MS footprint ≤20 m); context = local building
  density (res-9), MMI (nearest ShakeMap contour, max of both events), distance to coast.
  Context features implement RQ3c's reliability-aware weighting.
- **Label**: CEMS {2,3} point within 20 m of the building (20 m not 10: median NN spacing
  9.7 m makes 10 m labels position-noisy for training; evaluation of the paper's identity
  claims stays at r=10 elsewhere).
- **Crowd handling**: buildings in crowd-majority-damaged hexes with NO CEMS point get
  training weight 0 (not punished as negatives for finding CEMS gaps); reported both ways.
- **Validation**: spatial block CV — GroupKFold on H3 res-7 blocks (~5 km²). All reported
  numbers are pooled out-of-fold. Random-split numbers are NOT reported (leakage).
- **Models**: logistic regression (readable weights) + random forest (interactions,
  importances). Baselines to beat, same label & region: the k-of-6 dial points and the best
  single product.
- **Metric**: precision-recall curve + average precision (PR-AUC); class imbalance ~4%.
- **Caveat carried**: weights are event-specific calibration; framed as "what was learnable
  in-event", not a transferable model.
