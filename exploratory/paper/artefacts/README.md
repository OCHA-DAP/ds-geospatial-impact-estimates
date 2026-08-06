# artefacts/ — analysis scratchpad (git-ignored)

Working space for the **performance analysis** (products vs CEMS ground truth). This whole tree is
git-ignored (via `exploratory/paper/*`). Iterate freely here; when a result is understood and
distilled, the *chosen* figures/numbers graduate into the paper. Nothing here is a deliverable —
it is the lab bench and the memory of what we tried.

## Convention — one folder per research question

```
artefacts/
  RQ<N>-short-title/
    scripts/     # runnable .py — read immutable snapshots, save figs, print numbers
    figs/        # generated PNGs (also git-ignored; regenerate by running)
    NOTES.md     # running log: what we tried, what we found, dead ends, decisions
```

Keep `NOTES.md` current per RQ — it is how we remember iterations across sessions. Log the
**dataset basis** each script used (see RQ0) so numbers are comparable.

## Research questions

- **RQ0 — matching basis & methodology.** The crux decision: score against CEMS using the existing
  gold 20 m-snap-to-Overture model, or a paper-specific tighter building match? Includes the
  snap-sensitivity check. *Settle this first — it defines the join every other RQ uses.*
- **RQ1 — CEMS coarse blocks (`builtUpA`) as truth.** Areal / aggregate agreement per source
  (per block / hex / admin). The "early coarse estimate" reference. **Do this first.**
- **RQ2 — CEMS footprint points (`builtUpP`) as truth.** Building-level confusion matrix
  (precision / recall / F1) within the *shared analysed extent* per source. The fine reference.
- **RQ3 — prioritization skill & error structure.** Rank agreement (Spearman/τ, top-k) + the
  noise-vs-bias test (over-detection ratio, Moran's I, covariate regression). The paper's core
  thesis. Includes the Microsoft high-FP named investigation.
- **RQ4 — UNEP debris within fully-enclosed admin units.** Fair comparison where the analysed-edge
  ambiguity is negligible (La Guaira etc.); mass→damaged threshold + enclosure assumption stated
  explicitly.
- **RQ5 — consensus ensemble (building-level).** Can k-of-n voting across products improve the
  *building map* (precision at acceptable recall) vs the best single product? Cross-sensor vs
  same-sensor pairing as the error-correlation measurement. Classification only (ranking already
  good, RQ3a); see `RQ5-ensemble/DESIGN.md`.
- **RQ6 — DIY Sentinel-1 CCD (planned).** Full threshold-swept curve with stability-normalized
  coherence + object-level post-processing: can any operating point reach the cross-modal
  ensemble's? Competing predictions logged; spatial holdout mandatory; Caracas/Santa Cruz extents
  as negative controls. See `RQ6-diy-sar/DESIGN.md`.

## Scope (set 2026-07-05)

- Ground truth: **CEMS** — coarse blocks first, then footprint points.
- Scored sources: **IMPACT (v1 raster + v2 vector), OSU, Microsoft** (have analysed extents),
  and **UNEP debris** within enclosed admin only.
- De-prioritized: **HOT_OSM, DISHA** — no analysed AOI (cannot bound the comparison area fairly).

## Reproducibility

Read from immutable bronze/silver/gold snapshots (ADR-0005). Each script states its dataset basis
and CEMS snapshot/version. Uses the repo env: `uv run --group etl python <script>`.
