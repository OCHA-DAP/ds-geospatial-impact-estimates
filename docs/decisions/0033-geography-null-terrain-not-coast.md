---
status: "accepted"
date: 2026-09-17
deciders: zackarno
amends: 0025-damage-product-evaluation-method
---

# The geography null uses building density, terrain and shaking; coast distance is dropped

## Context and Problem Statement

ADR-0025 gives the evaluation a *hindsight geography null*: a model of context variables fitted to
the event's own damage labels, so that a product's precision can be read against "what geography
alone already explains". Its variables were building density, distance to the coastline and USGS
ShakeMap intensity. External review (L. Milano, 2026-09) and the author objected that coast
distance is event-specific: it predicts damage here because the damaged strip is a coastal
debris-flow fan, and a reader could say the null was "chosen because it works in La Guaira".

A covariate ablation on 2026-09-02 (`RQ8-learned-fusion/rq8d_null_ablation.py`, frozen as
`rq8d_null_ablation.csv`; findings register entry "RQ8d") tested nine feature sets on the frozen
core buildings through the exact null pipeline:

| null features | building F1 | ranking ρ (res 8) |
|---|---|---|
| density alone | 0.086 | 0.54 |
| density + coast + MMI (v3's null) | 0.127 | 0.65 |
| density + elevation + MMI | 0.143 | 0.71 |
| density + slope + elevation + MMI | 0.144 | 0.72 |
| density + slope + elevation + coast + MMI | 0.151 | 0.72 |
| density + SoilGrids sand/clay + MMI | 0.085 | 0.54 |

Coast was never load-bearing: density alone sits at the bottom of the product band, and once slope
and elevation are in, coast adds ~0.007 F1. A null built only from globally available terrain
(Copernicus GLO-30) is *stronger* than the published one, so no product was flattered by the
change. Elevation has named physics here: the low surfaces are the debris-flow fans USGS mapped
after the 1999 Vargas disaster (Wieczorek et al., OFR 01-0144). Global soil products cannot see
inside a city (86% of core buildings sample SoilGrids no-data); local geology (FUNVISIS
microzonation, INGEOMIN, the 1999 fan plates) exists only as PDF cartography and is parked.

The brief's text had meanwhile described the null as "building density and terrain" while its
numbers still came from the coast model, and carried a TBD marker for the unresolved framing.

## Considered Options

1. **Keep the coast null, describe it truthfully.** Prose-only; leaves the brief on a variable the
   authors themselves consider event-specific.
2. **Switch the brief's null to density + slope + elevation + MMI (chosen).** Refit the null and,
   because ADR-0025 defines the null as "the fusion with the product inputs removed", the fusion
   too, so the two keep the same context set. v3 stays frozen on the coast null.
3. **Drop the null from the brief entirely.** Rejected: ADR-0025's point stands — without it,
   "precision 0.08" has no interpretation — and ADR-0029 already sized it to two sentences.

## Decision Outcome

Option 2.

- **One definition.** `exploratory/paper/pipeline/context.py` computes the context features
  (`NULL_FEATURES = density9, slope, elev, mmi`); the ranking module and the archived fusion and
  as-delivered-baseline scripts import it instead of carrying their own copies (four copies
  existed). Coast distance remains computable (`include_coast=True`) for the archived ablation and
  oracle comparisons only.
- **Narrow Snakemake dependency.** `context.py` is an input only to the rules that fit a null
  (`ranking`, `rq8`, `rq8b`), never to `scorecards`/`facts`, so a null-feature change cannot
  rerun the precision or pair numbers. Measured rerun on 2026-09-17: fusion 3 × ~6 min, as-delivered
  baseline 2 × ~20 min, ranking ~30 min, everything else minutes.
- **Fail loudly on the DEM.** Tiles are fetched per 1° cell the points touch (three for this
  extent), mosaicked, and sampled; any point outside the mosaic or on no-data raises. GLO-30 codes
  sea as 0 m without a no-data flag, so a building mis-located into the sea would read 0 m; buildings
  are on land by construction and this is accepted.
- **Leakage check.** A smooth covariate is the case where spatial-block cross-validation can leak
  structure across block edges (OPEN-ITEMS item 1). The r = 10 fusion/null is also refit with a
  500 m train/test buffer (`rule rq8_buf`, own `_buf500` suffix, frozen) and the brief reports both.
- **MMI stays.** It is flat across the core (contributes nothing there) but carries a quarter to a
  third of the weight across delivered footprints; it is the hazard term and dropping it would make
  the null geography-only in name.
- **Generalizable means the inputs, not the coefficients.** The null is refit per event; the claim is
  that its inputs exist on day zero anywhere, not that a fitted model transfers.
- **Records.** The rq8d ablation is not rerun; it is the frozen justification. The oracle check gains
  an explained exception for null metrics (the archived rq3f oracle used coast). The frozen v3 keeps
  its coast null; its imported appendix in the brief is now "adapted from" v3 and reports the terrain
  null.

### Measured effect (2026-09-17 rerun, core region, r = 10 m unless stated)

| quantity | coast null (v3) | terrain null (brief) |
|---|---|---|
| null F1, logistic | 0.172 | 0.159 |
| null F1, random forest | 0.142 | 0.164 |
| fusion F1 | 0.371 | 0.357 |
| flat voting F1 | 0.323 | 0.323 (unchanged; no context inputs) |
| null area-ranking ρ, res 8 | 0.644 | 0.680 |
| as-delivered day-zero AP, MS / IMPACT / UH | 0.066 / 0.061 / 0.072 | 0.089 / 0.083 / 0.087 |
| null F1 under a 500 m CV buffer | — | 0.157 |
| nested-cut null F1 (vs hindsight) | 0.159 (vs 0.172) | 0.129 (vs 0.159) |

So the terrain null is stronger at ranking areas and across the delivered footprints (the frames where
"geography explains most of it" is claimed), and at the building level it is stronger under the forest
and slightly weaker under the logistic. The rq8d ablation had predicted a uniform gain because it ran
the rq3f ranking pipeline (no sample weights, no product columns), not the rq8 fusion pipeline.

**Reported learner.** ADR-0025 says report the stronger learner per frame. In the core the forest is now
marginally stronger (0.164 vs 0.159). The logistic stays the reported null anyway, because the paired
bootstrap differences, the nested-threshold check and the "fusion = null + products" construction are all
built on it; the brief quotes the forest value beside it wherever the null is quoted. Product numbers,
voting numbers and all product/rule confidence intervals are byte-identical to the frozen run.

### Consequences

* Good: the benchmark is defensible as generalizable in its inputs; the TBD in the brief is resolved by a
  decision rather than a paragraph; the feature set has one home; the leakage check is now a standing
  artefact rather than an open item.
* Good: at area ranking and as delivered — where the "products add little beyond geography" claim
  lives — the null got stronger, so the claim is more conservative, not less.
* Bad: at the building level the reported (logistic) null is 0.013 F1 weaker, which very slightly
  flatters the products in the best-F1 figure; the forest value is disclosed to bound that.
* Bad: the null's operating point is more sensitive to the hindsight cut than before (nested −0.031 F1
  vs −0.013); the brief reports both.
* Bad: every null and fusion number in the brief moves; v3 and the brief now disagree on the null's
  definition, which the brief states explicitly.
* Bad: adds `rasterio` to the `paper` dependency group and a network fetch (cached) on first run.
