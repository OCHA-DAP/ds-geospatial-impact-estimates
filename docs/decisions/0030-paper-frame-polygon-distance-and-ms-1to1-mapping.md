---
status: "proposed"
date: 2026-09-10
deciders: zackarno
amends: 0029-frozen-v3-and-technical-brief
---
# Paper scoring frame: polygon-distance matching on the shared base, Microsoft mapped 1:1

## Context and Problem Statement

The paper scores every product against Copernicus EMS damage points on one shared Overture
building base, so that products can be compared with each other and combined by voting
(ADR-0001). Two implementation choices were never recorded as decisions and were found, during
the 2026-09 internal review of the technical brief, to move the numbers materially:

1. **Where distance is measured from.** Gold `building_flags` stores each Overture building as a
   lon/lat point, so every paper script matched a flagged building to a CEMS point by
   *centroid* distance within the 10 m radius. The brief's appendix table `tbl-frames` asserted
   that centroid and delivered-geometry matching "agree to within 0.005"; the table turned out
   to be the centroid values rounded to two decimals, not a second measurement. A six-product
   run (`artefacts/RQ0-matching-basis/native_rerun/`) shows delivered-geometry scoring runs
   +0.02 to +0.04 precision and +0.11 to +0.19 recall above centroid scoring for every product,
   because a 10 m disc around a centroid is a smaller catch zone than the footprint plus 10 m,
   and CEMS points are digitized onto buildings, not their centres.
2. **How Microsoft's own footprints were mapped onto Overture ids.** Venezuela gold uses
   `ST_Intersects` (`pipelines/harmonize_common.py`): any Overture footprint touching a damaged
   Microsoft polygon is flagged. Because the two footprint sets were drawn independently, this
   bleeds flags onto neighbours: 7,949 delivered polygons in the core become 9,139 flagged base
   buildings (+16%, 1,309 buildings Microsoft never flagged). The Colombia pipeline
   (`harmonize_common_co.py`) already maps 1:1 by point-on-surface containment; the divergence
   was never recorded or back-ported. Measured effect in the core: Microsoft precision
   0.113 -> 0.122, F1 0.191 -> 0.204 (polygon frame); voting rules move <= 0.01 F1.

The paper is unpublished; the brief and the scroll story are in internal review. Fix the frame
now, or document it as a caveat?

## Decision Drivers

* Correctness of the matching rule: a CEMS point on a building should match that building
  regardless of its size.
* Fairness across products: one shared base (so combination rules are defined and finer
  footprint bases are not rewarded) without a rule that penalises one provider's geometry.
* Reproducibility: every number in the paper must come from a frozen artefact under one stated
  frame, and the previous frame must remain reproducible.
* The dashboard/gold must not change (served basis; ADR-0029's OSU v0 pin sets the precedent for
  paper-side overrides).

## Considered Options

1. Keep the centroid frame and the gold Microsoft mapping; delete the false table; add a
   quantified caveat citing the native_rerun folder.
2. Switch the paper to polygon-distance matching on the shared base and map Microsoft 1:1 by
   max-overlap, both as paper-side switches in `lib/gie_paper.py`; refreeze the paper artefacts.
3. Score every product on its delivered geometry (fully native). Rejected: no shared building
   list, so k-of-6 voting and the fusion/null models are undefined, and finer footprint bases
   (UNEP/GBA) would be penalised relative to coarser ones.
4. Change gold itself to the 1:1 rule. Deferred: changes the dashboard basis mid-event; belongs
   with a pipeline release, not a paper revision.

## Decision Outcome

Option 2. Two module constants in `exploratory/paper/artefacts/lib/gie_paper.py` define the
frame — `PAPER_FRAME = "polygon"` and `MS_MAP_RULE = "max_overlap"` — and are deliberately not
environment-driven, so a script cannot run in a mixed frame. `gp.buildings()` replaces the
per-script `points_from_xy(lon, lat)` idiom and returns Overture polygons (from the local base
cache) under the polygon frame; `gp.building_flags()` overrides `ms_dmg` with the frozen id set
`lib/ms_1to1_ids.csv` (built by `lib/build_ms_1to1_ids.py`: largest-overlap building per
Microsoft footprint; ties broken by centroid distance then id; orphans listed in
`ms_1to1_orphans.csv`). Cell assignment (H3) keeps using lon/lat — it is geometry-neutral.

Path back: the frozen-v3 state is tagged `paper-frozen-v3-centroid`; setting the two constants
to `"centroid"` / `"intersects"` reproduces it from the same code. The refreeze runs on branch
`paper-polygon-frame`, one script per commit, so every artefact's change is diffable.

### Consequences

* Good: the matching rule matches how the reference was made; single-product scores agree with
  delivered-geometry scores to within ~0.01 F1; the "combining roughly doubles F1" result holds
  inside one fair frame (5-of-6 F1 0.38 vs best single 0.20 at r = 10 m).
* Good: no provider is penalised by our mapping; Venezuela and Colombia use the same 1:1 logic.
* Bad: every level in both documents changes (single-product precision 0.07–0.13 instead of
  0.045–0.093 at 10 m; the dial reads 5% -> 79% instead of 3% -> 64%); all tables, figures and
  prose must be re-pointed, and the Hypothesis review threads on the brief reference the old
  numbers.
* Bad: the polygon frame needs the ~640 MB Overture base cache locally; scripts fail loudly
  without it rather than falling back to centroids.
* Neutral: the two ADRs numbered 0029 (this repo has a numbering collision) are both left as
  is; this ADR amends the frozen-v3 one.

## More Information

Evidence: `exploratory/paper/artefacts/RQ0-matching-basis/native_rerun/` (native vs centroid,
shared-base polygon, Microsoft mapping rule, max-overlap diagnostics). Review that surfaced it:
Hypothesis group `ppY7JE2k`, 2026-09-09. Colombia's 1:1 rule: `pipelines/harmonize_common_co.py`
(cites ADR-0015, which concerns IMPACT v2's Overture-twin footprints, not Microsoft).
