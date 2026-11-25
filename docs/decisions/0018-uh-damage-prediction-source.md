---
status: "accepted"
date: 2026-07-06
deciders: zackarno
---

# Integrate the UH damage-prediction source: containment-project its id-less footprints, derive its missing extent

## Context and Problem Statement

A University of Houston group (delivery contact `dksingh@cougarnet.uh.edu`)
provided a per-building damage prediction for the June 2026 VE earthquake:
478,467 footprints across eight coastal AOIs, each graded intact / damaged /
destroyed. Two properties make it unlike our existing sources and force a design
choice each:

1. It **includes intact buildings**, so — unlike the detected-only sources
   (HOT / DISHA / UNEP debris) — it *could* carry the **full coverage-aware metric
   set** like Microsoft, IF an analysed-area extent existed. But the provider shipped
   **no analysed-area mask**, and the footprints don't imply one honestly (below).
2. Its footprints are effectively our **Overture base** (~98% have an Overture twin;
   see `exploratory/0004`) but carry **no feature id**, so damage cannot be
   projected onto the base by an id-join the way OSU/Microsoft are.

## Decision Drivers

* Project every source onto the shared Overture base (ADR-0001) so the viewer
  compares them in the same units.
* Don't invent data: a footprint with no Overture twin should not be force-attached
  to a wrong neighbour.
* Coverage / fraction / extrapolation are only meaningful with an honest extent that
  reflects *where UH actually looked*, not an inflated hull.

## Considered Options

**Damage projection (id-less footprints):**
* A. **Centroid-containment** — flag the base building that `ST_Contains` the
  footprint's `ST_PointOnSurface` (the impact_v2 rule, ADR-0015).
* B. **Centroid-snap** — snap each footprint centroid to the nearest base within
  20 m (the UNEP-debris / CEMS-point rule).

**Defining the analysed set (no AOI mask shipped).** "Analysed" can be a *polygon*
(what Microsoft/CEMS supply) OR the *set of buildings the source classified*:
* C. **Buffered union polygon per AOI** — dilate every footprint, union, erode back.
* D. **Convex / concave hull polygon per AOI** — one smooth polygon per AOI.
* E. **Ship detected-only** — no analysed set; damaged counts + footprints only.
* F. **Use UH's own classifications as the analysed set** — every footprint is graded,
  so the base buildings UH classified (any grade, by containment) ARE the analysed set;
  no polygon needed.

## Decision Outcome

**Damage projection: A (centroid-containment).** UH footprints are Overture
geometry, so a point-on-surface lands on the exact twin — a clean, id-free 1:1 with
no edge-neighbour over-flag. `exploratory/0004` confirms 98.06% of damaged
footprints match a twin; where UH is finer than Overture several collapse onto one
base (up to 12:1), so the Overture-projected damaged count (**74,780**) sits ~7.6%
below native (**80,913**). That is the expected two-base situation (ADR-0017), not
a defect: snap would collapse identically *and* mis-attach the 1.94% twinless
footprints. We therefore **report UH on two bases** — Overture-projected for
cross-source comparison, native for attribution. Damaged/destroyed carry the worst
grade as `uh_class` (worst-grade-wins, like `cems_class`).

**Analysed set: F (UH's own classifications).** The key realisation: UH doesn't need
an analysed *polygon* at all, because it grades *every* footprint — so the buildings it
classified ARE the analysed set. In `harmonize_common`, `uh_analysed` = a base building
that contains ANY UH footprint's point-on-surface (grade irrelevant); `uh_dmg` = one
whose worst grade is damaged/destroyed. Then `coverage = analysed / exposed` and
`damage fraction = damaged / analysed` fall straight out of the common model — computed
directly from the provider's per-building layer, no fabricated geometry. It is robust to
imperfect Overture projection: numerator and denominator project the same way, so the
~2% twin-miss and finer-footprint collapse cancel in the *ratio* (they only shift
absolute counts — ADR-0017, exploratory/0004). There is **no extent outline** for UH
(no polygon to draw); its coverage is shown by the buildings themselves.

This supersedes two earlier iterations: (1) a derived buffered-union polygon (C) —
fragmented, and it briefly rendered CEMS's AOI via a silent fallback in
`load_source_extent` (since fixed); (2) a detected-only stop-gap (E) — which needlessly
threw away a damage fraction we *can* compute honestly. The convex/concave hulls (D)
were rejected outright: they balloon to ~600 km² (vs a 191 km² footprint hull), bridge
unbuilt mountainside, and, being per-AOI, overlap each other. The provider has been
asked for their own AOI polygons; if they arrive, they'd refine `coverage` (a larger,
possibly sparser analysed denominator) but the damage *fraction* would barely move.

### Consequences

* Good — UH is coverage-aware (coverage / damage fraction / extrapolation) with nothing
  fabricated: the analysed set is the provider's own per-building classifications.
* Good — reuses a proven, already-audited projection rule (ADR-0015) and needs no
  polygon, so there is no funky extent to render or defend.
* Neutral — UH is the first coverage-aware source with no extent outline; its coverage
  is read off the building points, not an AOI boundary.
* Bad — the −7.6% native↔Overture gap still needs explaining for absolute counts;
  mitigated by the two-base convention (ADR-0017) and cancels in the damage fraction.
* Neutral — attribution + method are now provider-supplied (**UH QuakeDamage**, a
  Singh & Hoskere deep-learning model over Overture footprints; quakedamage.github.io),
  which also confirms the footprints ARE Overture (feeds ADR-0019). The internal source
  id stays `uh`. Licence / redistribution terms are still to confirm, so the source
  stays staging-only until those land (do not promote numbers to prod).

## Pros and Cons of the Options

### A. Centroid-containment
* Good — clean 1:1 onto the exact Overture twin; no id; no over-flag; carries grade.
* Good — drops (rather than mis-attaches) the 1.94% of footprints with no twin.
* Bad — those dropped footprints are absent from the Overture-projected count (but
  present in the native count).

### B. Centroid-snap
* Good — tolerant of footprints with no exact twin.
* Bad — same finer-than-Overture collapse as A, *plus* it attaches twinless
  footprints to an arbitrary nearest neighbour — inventing damage locations.

### C. Buffered union
* Good — hugs the assessed built area; the tightest of the derived options (191 km²).
* Bad — fragmented and visually poor (dense AOIs shatter into hundreds of pieces).

### D. Convex / concave hull
* Good — clean, single smooth polygon per AOI.
* Bad — balloons to ~600 km², bridging unbuilt mountainside, and per-AOI hulls
  overlap each other — trades "fragmented" for "overstated and wrong".

### E. Detected-only
* Good — ships nothing fabricated.
* Bad — discards a damage fraction we can compute honestly from the classifications.

### F. Classifications as the analysed set (chosen)
* Good — real coverage + damage fraction, no polygon, straight from the provider's data.
* Good — the fraction is robust to imperfect Overture projection (ratio cancels the miss).
* Neutral — no extent outline; coverage is shown by the building points themselves.

## More Information

Evidence: `exploratory/0004-uh-containment-validation/`. Builds on ADR-0001
(common Overture base), ADR-0015 (the containment rule), ADR-0017 (two-base
counts). Revisit if the provider ships an official analysed-area mask (replace the
derived extent with it) or an id-keyed footprint set (switch to an id-join).
