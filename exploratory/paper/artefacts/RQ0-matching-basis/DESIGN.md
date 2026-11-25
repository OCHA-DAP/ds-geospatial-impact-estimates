# RQ0 — Analysis system & matching basis (the design that gates every other RQ)

Status: **PROPOSED — awaiting sign-off before we compute metrics.** See `../DATA_MAP.md` for schemas.

## Decision: do NOT score against the viewer's gold `facts.parquet`

It is a comparison-*visualisation* artifact, not a validation dataset. Disqualifying for primary
evidence because it: (1) snaps **CEMS itself** onto Overture — 2.6% of `builtUpP` points drop, 12%
collapse — so you'd score against an Overture projection of CEMS, not CEMS; (2) conflates detection
error with footprint-granularity collapse (ADR-0017), penalising finer-footprint products as an
artifact; (3) explodes coarse `builtUpA` blocks into fabricated per-building labels; (4) uses
worst-grade-wins + DISTINCT-id, discarding multiplicity; (5) contains `damaged_extrapolated`
(modeled, not observed) damage. We **report** the gold/Overture comparison as the *operational*
baseline (flagging the artifact), but the paper's numbers come from a purpose-built match on the
immutable **silver** snapshots.

## The primary method: dual-anchored pairwise native matching

Match each product to CEMS **natively** — CEMS stays bare points/blocks, each product keeps its own
footprints (Overture for OSU/IMPACT since that genuinely *is* their base; MS's own; UNEP's GBA). No
forced common base, no Overture snap. Compute precision and recall from **opposite anchors**, so we
never need a true-negative count or a shared building universe:

- **Recall** — for each CEMS damage point inside `(CEMS_extent ∩ product_extent)`: is a
  product-flagged building within radius *r*? → TP / FN. Denominator = CEMS points.
- **Precision** — for each product-flagged building inside `(CEMS_extent ∩ product_extent)`: is a
  CEMS damage point within *r*? → TP / FP. Denominator = product buildings.
- **F1** from the two. No TN needed (correct for extreme class imbalance — TN is a huge
  uninformative background).

**The one assumption** (which the ground-truth claim already licenses): *within CEMS's analysed
extent, a building with no CEMS feature nearby is genuinely undamaged*, so a product flag there is a
true FP — not an un-assessed unknown. Stated explicitly in the paper.

Parameters, stated with sensitivity (not inherited from the viewer's 20 m):
- **Match radius r = 10 m primary, {5, 20} m sensitivity.** Report drop/collapse rates at each.
- Polygon products: containment first, else nearest within *r*. Point/id products: nearest within *r*.
- Coverage restriction is mandatory and per-pair (a product is only accountable where it *and* CEMS
  both looked).

Why dual-anchor beats a shared-Overture confusion matrix: it isolates **detection skill** from
footprint granularity, keeps the reference undistorted, and treats all five sources uniformly
despite heterogeneous keys. Cost: no TN-based metrics (specificity/accuracy) — which we don't want
anyway for rare-event detection.

## Per-RQ method

- **RQ1 — CEMS coarse blocks (`builtUpA`) as truth [DO FIRST].** Blocks are damaged *areas*, so they
  give an areal negative for free: within the initial-product analysed extent, a product building
  **inside** a block = predicted-damaged-in-damaged-area (TP), **outside** all blocks = FP; a block
  with no product building = FN. Score areally / per-block + per-hex; **never** explode blocks to
  per-building labels. This is the "early coarse estimate" reference.
- **RQ2 — CEMS points (`builtUpP`) as truth.** The dual-anchor method above, per source, at
  r∈{5,10,20}. Headline precision/recall/F1 table. Per-grade cut (Destroyed / Damaged / Possibly).
- **RQ3 — prioritization skill & error structure.** Aggregate to h3 (res-8) and admin: rank
  agreement (Spearman/τ, top-k concordance) of damaged-density vs CEMS; then the noise-vs-bias test
  (over-detection ratio, Moran's I on residuals, regression on non-damage covariates). Uses
  `damaged_detected` densities only — never extrapolated. Includes the Microsoft high-FP named case.
- **RQ4 — UNEP debris, enclosed-admin only.** No AOI → restrict to admin units *fully interior* to
  the hard-hit zone (La Guaira / Caraballeda), where edge-of-analysis ambiguity is negligible;
  assume full coverage there and **state it**. Threshold `debris_tonnes` > cutoff → damaged; match
  GBA-native to CEMS points (dual-anchor). Report as detected-overlap, flagged as assumption-laden.

## Concrete build tasks (in order)

1. **Shared helpers** (`artefacts/lib` or per-RQ `scripts/`): silver readers (DATA_MAP snippets),
   analysed-extent intersection, dual-anchor matcher (radius param), metric calc. Reused across RQs.
2. **Re-materialise IMPACT v1** to a distinct silver path (re-run `harmonize_impact_sar.py`, or
   re-derive from bronze `.tif`) so v1 and v2 score side by side. *(Blocker for the v1/v2 story.)*
3. RQ1 coarse-block areal scoring → figs + NOTES.
4. RQ2 point-level dual-anchor → precision/recall/F1 table + radius sensitivity.
5. RQ3 aggregate rank + error-structure.
6. RQ4 UNEP enclosed-admin.

## Open questions for sign-off
1. **Match method** — dual-anchor pairwise-native (recommended) vs shared-Overture confusion matrix?
2. **Radius** — 10 m primary / {5,20} sensitivity OK?
3. **"Possibly damaged" (class 1)** — count as damaged-positive in the binary, or treat as
   uncertain/exclude? (Affects every recall number; recommend: report both, headline = {2,3}=damaged.)
4. **IMPACT v1** — worth the re-materialisation cost to score both v1 and v2? (recommend yes.)
5. **Scoring universe for precision** — accept the "no CEMS feature in extent ⇒ undamaged" assumption?
