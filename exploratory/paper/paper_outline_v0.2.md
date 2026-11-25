# Paper outline — draft v0.2 (2026-07-15)

> Supersedes v0.1 (`paper_outline.md`). What changed: the analyses are done (RQ0–RQ7 in
> `findings.qmd`), the thesis widened from "noisy products can still prioritize" to a
> three-act arc, the source set is FROZEN, and the include/cut decisions are recorded here.
> [DECISION] marks the remaining open choices.

## Working title

*One product tells you where; six tell you which buildings to check first: a multi-reference
evaluation of rapid satellite damage products in the 2026 Venezuela earthquake.*

(Alternative, closer to v0.1: *Evaluation of near-realtime damage analysis products in the
Venezuela earthquake response* — safer, duller. [DECISION])

## The three-act spine

**Act A — a single product ranks areas well but cannot map buildings.**
Per-building precision is structurally low (floors 0.03–0.12) and over-detection heavy
(5–26×), yet area ranking survives: top-20 concordance ~0.8 at triage scale, improving with
aggregation. The error is spatially structured but *severity-aligned* (toward coast, up with
MMI) — the benign kind; density/urban-form bias is ruled out by the exposure-offset design.
Exception logged: Microsoft's localized west-strip cluster, adjudicated by the MapSwipe
crowd as genuine false positives.
*Evidence: RQ2, RQ3, RQ3b (+per-area addendum), RQ7 strip-scale adjudication.*

**Act B — you cannot tune your way out, but you can vote your way out.**
The modality floor, shown three independent ways: same-sensor consensus plateaus
(IMPACT∧OSU), a from-scratch tunable SAR pipeline saturates below the ensemble (RQ6), and
Microsoft's own confidence axis is flat (RQ2d). Cross-modal k-of-6 voting, by contrast,
turns vote count into a **calibrated confidence dial** — monotone against all three
references — with **3–4-of-6 as the practically useful triage tier** (best F1; field recall
0.74–0.87). The unanimous end (6-of-6, adjusted precision ≈0.93 at 9% recall) is presented
as a calibration anchor and CEMS-gap instrument, explicitly NOT an operating rule. The
active ingredient is error *decorrelation across modalities* (mechanism, NOT a recipe —
stated with the one-event/one-pair generalization caveats).
*Evidence: RQ5, RQ5b, RQ6, RQ2d, RQ7b.*

**Act C — what everything misses, and how we know.**
A three-reference triangulation with disjoint failure modes: CEMS (both-sided, within its
extents), MapSwipe crowd (false-alarm side, on MS/fAIr seeds), ChatMap field reports
(miss side, anywhere). Findings: the grade gradient is universal — satellite damage
detection ≈ *destruction* detection; CEMS itself matches only 49% of field-reported
'significant' damage (so all published precisions are floors); ~11% of field-confirmed
damage (inland El Junquito/hills) was missed by every product.
*Evidence: RQ2e, RQ7b, RQ2c (UH inland behaviour as the cautionary tale).*

## Frozen source set ([DECISION: freeze date = 2026-07-15, snapshot = current silver])

| product | modality | analysed AOI | roles |
|---|---|---|---|
| Microsoft AI4G | optical AI | yes | member; confidence + num_observations deep-dive |
| IMPACT v2 | S1 coherence | yes | member |
| OSU/NASA | S1 coherence | yes | member; max-recall profile |
| UH QuakeDamage | vision AI (per ADR-0018) | derived | member; weak-single/strong-voter story |
| LIST (WFP/LIST/CERN) | ResNet pre/post [modality TBC — flag #14] | yes | member |
| UNEP/OCHA debris | SAR debris mass | none — *stated coverage assumption in core region* | member (RQ5b) + RQ4 |
| HOT fAIr, DISHA | optical AI | none | availability inventory only; ChatMap hit-rate one-liners |
| IMPACT v1 | S1 raster | — | DROPPED (user decision 2026-07-15) |

References: CEMS EMSR884 (latest monitoring per AOI — the `is_latest` freeze fix),
MapSwipe crowd (bronze, re-runnable loader), ChatMap field points (415).

## Section map (with include/cut decisions)

1. **Introduction** — the first-days information gap; the product explosion; the two
   distinct user questions (where vs which buildings). *From v0.1 §1, tightened.*
2. **Event & products** — event context; frozen source table above; availability/licence
   inventory (fAIr + DISHA live here and only here).
3. **Reference data & the triangulation** *(new section — was scattered)* — CEMS as ground
   truth + its two bounds; MapSwipe campaign mechanics (0/1/2 votes); ChatMap; the
   triangle-of-failure-modes figure. RQ2e's CEMS-completeness result lands HERE (it
   qualifies everything downstream).
4. **Methods** — dual-anchor matching (+ the QMD diagram); coverage-restriction rule;
   exposure-offset GLM + permutation Moran (the two explainer figures); H3 units and why;
   construction-vs-scoring basis (ADR-0017). CUT: bias_rho history, cache/tooling.
5. **Results A — where** (RQ3 ranking, RQ3b error structure, MS west-cluster + crowd
   adjudication). TRIM: RQ1 coarse blocks to one paragraph (severity-gradient note);
   per-area Moran table to supplementary.
6. **Results B — which buildings** (RQ5b six-member frontier + tiering table + H1
   sensor-pairing; modality-floor triptych folded into ONE subsection: IMPACT∧OSU +
   RQ6 curve + RQ2d flat confidence). TRIM: RQ6 object-clustering null to one sentence;
   RQ4 to one fair-comparison paragraph + row.
7. **Results C — what everything misses** (grade gradient, CEMS gap, inland gap,
   UH inland cautionary tale from RQ2c).
8. **Latency & availability** — [GAP: the timeline needs provider-date confirmations;
   currently upper bounds only. The latency-accuracy frontier is the one PLANNED figure
   with no data behind it yet.]
9. **Discussion** — operational tiering recommendation; mechanism-not-recipe framing;
   consensus-as-CEMS-gap-detector; what a "damage fusion" service would need (nod to the
   viewer as working prototype).
10. **Limitations** — one event/one geography; UH & LIST modality confirmations pending;
    crowd = volunteers on unknown-vintage imagery; ChatMap undated + severity-skewed;
    centroid-vs-native basis deltas; no CIs yet [GAP: bootstrap].
11. **Conclusions & recommendations.**

## Remaining work queue (ranked)

1. ~~CEMS latest-only reconciliation~~ → freeze batch running (flag #13).
2. Timeline provider-date confirmations — **blocks §8; emails are drafted-in-concept, need
   sending (user).**
3. Pop-weighted prioritization (one script; connects Act A to triage reality).
4. Early-totals vs consolidated CEMS ("how wrong were the first numbers") — one table.
5. Grade-stratified CEMS recall (flag #12) — corroborates Act C from the CEMS side.
6. Bootstrap CIs on headline numbers (flag: reviewers will ask).
7. LIST + UH modality confirmations (flags #14, H1 pair-typing).
8. Stretch: Myanmar replication of the cross-vs-same-sensor contrast (external validity).

## Cut list (explicit, so nothing silently returns)

- bias_rho and its retraction (internal lab history).
- El Junquito MapSwipe project detail (reference growth, not findings).
- RQ6 HyP3 coherence rerun (parked — future work sentence).
- Per-area Moran, radius sensitivities, RQ5 four-member tables → supplementary material.
- Mass/tonnage debris analytics (viewer feature, not paper).
