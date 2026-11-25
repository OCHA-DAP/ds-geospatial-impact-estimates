# RQ0 — running notes

## Cloud/no-data robustness check (2026-07-20) — `rq0_cloud_unknown_robustness.py`

Question (user-raised): MS's merged file carries per-building `unknown_pct` (fraction of the
building buffer that was cloud/no-data). Harmonize drops it, and the valid-area mask does
NOT excise cloud holes (99.4% of majority-obscured buildings sit *inside* the mask — it is
a scene-footprint union, not a cloud mask). So no scoring step ever accounted for
per-building visibility. Does that bias the frozen MS numbers?

Result: **negligible**, in the exact rq5b core-region frame:

- 3.6% of the 72,162 buildings are majority-obscured (`unknown_pct > 0.5`); obscuration is
  *lower* on flagged buildings (0.4%) than intact ones (4.0%) — the model abstains under
  cloud rather than hallucinating into it.
- Precision **0.089 unchanged** at every visibility threshold (only 0.3% of in-region flags
  are on obscured buildings).
- Recall: exactly **1 of the 794 missed CEMS points** sits on an obscured building.
  (The CSV's R jump 0.459→0.508 under the filter is a *conditioning artifact* — it comes
  from requiring an MS building within 15 m of the CEMS point, which drops the ~10%
  stock-mismatch points; it is NOT a cloud effect. Do not quote it as one.)
- Side finding: cloud does **not** explain the west FP cluster — the single-scene west is
  the most cloud-free zone (2.8% obscured vs 5.2% in the two-scene east).

Implication: MS's small conservative bias under cloud means cloud-covered damage is
under-flagged, but at 3.6% of stock this is bounded and immaterial. No re-scoring needed;
logged as a robustness note in the register. Other products publish no per-building
visibility field, so the check is only possible for MS — another auditability point.
