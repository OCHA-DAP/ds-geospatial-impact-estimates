---
status: "accepted"
date: 2026-06-27
deciders: zackarno
---

# Overture exposure base scoped to full admin-1 states that coverage touches

## Context and Problem Statement

The common model reports, per admin unit, `total_buildings` (the unit's whole
building count) and `analysed_buildings` (those inside a source's valid area).
The total is the denominator for coverage % and damage fraction, so it must be
the *complete* building count for the unit. Originally we pulled the Overture
base only for the bboxes where we had a damage signal (the MS footprint extent
and each CEMS AOI). That made `total_buildings` unstable and incomplete: a unit's
count changed when an adjacent AOI was fetched (observed: Catia la Mar jumped
22,743 → 38,594), and any unit extending beyond a pulled bbox was undercounted.
How should we scope the Overture pull so per-unit totals are complete and stable?

## Decision Drivers

* `total_buildings` must be the complete, stable count for each adm1/2/3 unit.
* The set of pulled areas must be derived non-circularly (not from the base it
  produces) and must grow automatically as new coverage arrives.
* Bounded, idempotent, and resilient to a flaky remote scan + large writes.

## Considered Options

* Per-AOI bbox (where a damage signal exists)
* Whole country (Venezuela) up front
* Full extent of every admin-1 state that any source's coverage intersects

## Decision Outcome

Chosen option: **full extent of every admin-1 state that coverage intersects**.
If a source's analysed extent touches an adm1 state at all, pull that whole
state's Overture base; then every adm1/2/3 unit inside it has a complete total.
The state set is computed by intersecting the coverage geometries (CEMS analysed
swaths + Microsoft masks) with adm1 — independent of the existing base — and the
pull is idempotent (skip states already present), so new coverage in a new state
is picked up on the next run with no code change.

### Consequences

* Good, because per-unit totals are complete and stable for every level inside
  an affected state, and extrapolation/coverage denominators are trustworthy.
* Good, because it is coverage-driven and automatic — adding an AOI in a new
  state pulls that state next run; re-runs only fetch what's missing.
* Bad, because pulling whole states (esp. dense/large ones like Miranda) is a
  heavy one-time fetch of millions of buildings; mitigated by 150k-row chunked
  uploads, retries, and per-state skip-if-present.
* Neutral, because building counts are server-side only — the browser still gets
  just assessed buildings + admin aggregates, so map performance is unaffected.

## Pros and Cons of the Options

### Per-AOI bbox

* Good, because small and fast to pull.
* Bad, because per-unit totals are partial and shift as AOIs are added — the
  denominator is unreliable (the bug that motivated this ADR).

### Whole country up front

* Good, because every unit at every level is complete, including adm0.
* Bad, because it is the largest possible download/storage, most of it
  irrelevant to the event, and not incremental.

### Full affected adm1 states (chosen)

* Good, because complete for the levels that matter (adm1/2/3 within affected
  states) while bounded to the relevant region.
* Neutral, because adm0 totals stay partial — acceptable, since extrapolating a
  few city AOIs to a whole country is meaningless anyway (extrapolation is gated
  to fine units with ≥25% coverage).
* Bad, because the heaviest states are large pulls (see consequences).

## More Information

Implemented in `pipelines/ingest_overture.py` (`_affected_adm1_bboxes`) and run
in order by `pipelines/run_all.py`. Revisit if a future event needs complete
adm0 totals (→ widen to country) or if state-sized pulls prove too heavy
(→ clip each pull to the adm1 polygon to cut stored volume). Supersedes the
per-AOI scoping described in this repo's early ingest_overture.

**Update (2026-07-02, ADR-0015):** `_affected_adm1_bboxes` now (a) unions **every**
source's `analysed_extent` — not just CEMS + Microsoft — so no source can fall
outside the base (this had silently dropped ~0.6% of OSU: Portuguesa/Trujillo); and
(b) **clips each pull to the adm1 polygon** — the "cut stored volume" refinement
foreseen above. The re-run stays idempotent (skip-if-present), so it fetches only
newly-affected states.
