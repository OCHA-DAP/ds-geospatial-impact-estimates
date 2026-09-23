---
status: "accepted"
date: 2026-09-23
deciders: Zack Arno
---

# Gold offers two geometry methods; `snap` for polygonised-raster labels, recorded per code

## Context and Problem Statement

Gold dissolves each event code's silver polygons into label sets with
`make_valid` followed by `union_all`. On the full corpus this stalled: one
code (FL20220418ZAF, 20 polygons) ran for more than eight hours inside
`GEOSMakeValid_r`, and three queued codes were larger.

The cause is what UNOSAT's polygons are. They are polygonised rasters from an
automated flood classification: 93.6% of segments are axis-aligned (a
staircase along pixel edges), one feature holds tens of thousands of parts
and up to 1.8 million vertices, every sampled row is invalid with a ring
self-intersection (diagonal pixels touching at a corner), and the smallest
coordinate gap is 1e-9 degrees, which is sliver noise from reprojecting a
pixel grid into WGS 84. GEOS noding is superlinear in the vertices of ONE
geometry, so a 30-million-vertex feature costs hours where its parts would
cost minutes, and it runs on 100% of rows to repair the 9.5% that need it.

How do we make gold finish in hours rather than days without silently
changing what a label means, and while keeping the corpus traceable?

## Decision Drivers

* Gold must complete on a laptop in hours; the current method does not.
* The label geometry is a model target; any change in what it represents
  must be measured, bounded and recorded, never implicit.
* The 70 codes already built with the original method are not to be thrown
  away or silently mixed with a different method.
* Fail loud: an unknown method or a coverage union that GEOS rejects must
  not degrade quietly into something else.

## Considered Options

1. **Two explicit methods, `validate` (original) and `snap`, chosen per run
   and recorded per code in the run log.**
2. Replace the geometry path outright with the fast one.
3. Keep the original path and wait.
4. Skip validation entirely because silver "already validated".

## Decision Outcome

Chosen option 1. `validate` is byte-for-byte the original behaviour and
remains the default. `snap` explodes each feature to parts, repairs only the
parts that are invalid, snaps coordinates to a 1e-7 degree grid (about one
centimetre, far finer than any UNOSAT pixel), repairs again, reconstructs
each row's multipolygon by construction rather than union, and dissolves with
GEOS's coverage union, which a classified raster qualifies for because its
polygons are non-overlapping by construction. If GEOS rejects the coverage
union or returns invalid geometry, `snap` falls back to `union_all` for that
dissolve. The method is a CLI flag, `--geometry-method`, and every per-code
line in the run log carries `[geometry=<method>]`.

Measured on real silver layers (not fixtures):

| Measurement | Result |
|---|---|
| `make_valid` on a 3.8M-vertex row vs on its 25,667 parts | 391.5 s vs 13.6 s (28.7x) |
| `set_precision` vs `make_valid`, 84k-vertex layer | 0.24 s vs 1.83 s (7.6x) |
| `coverage_union_all` vs `union_all`, same layer | 0.03 s vs 0.90 s (30x) |
| Prototype end to end on the largest Somalia layer | 20.1 s vs 295.2 s (14.7x) |
| **Shipped `snap` vs `validate`, same layer** | **36.9 s vs 329.0 s (8.9x)** |
| Shipped `build_code`, whole code FL20170424HTI (4,926 polygons, 6 label sets) | 1.16 s vs 1.14 s; water area equal to 4 dp per label set; valid mask differs 1e-4 km² on 1,010 km² |
| Dissolved area, same layer | 5,681.131574 vs 5,681.131517 km² (1e-8 relative) |
| Symmetric difference, same layer | 0.0025% of area |

The symmetric difference is boundary jitter from the one-centimetre snap and
is far below the source raster's pixel size.

The shipped code is slower than the prototype because it repairs invalid parts
both before and after snapping: the precision reducer raises on a
self-intersecting ring, and snapping can itself create a self-touch. That
is roughly 20% of the speed-up spent on never crashing on real input.

On an ordinary code (Haiti 2017 above) the two methods run in the same time and
produce the same label-set count and areas: `snap` costs nothing where nothing
is pathological, and the gain appears only on the raster-derived giants.

**Which codes used which method is the record that matters.** Codes built
before this decision used `validate`. Codes built after it use the method
shown on their line in the run log; the run logs for this build are kept
under the work directory and summarised in `data_ledger.md`.

### Consequences

* Good, because the remaining corpus can finish in hours, on the machine we have.
* Good, because the original path is untouched and selectable, so any code can
  be rebuilt the old way for comparison with `--geometry-method validate --force`.
* Good, because the difference between methods is measured and bounded, and
  the method used is traceable per code rather than inferred.
* Bad, because the corpus is built with two methods. This is deliberate and
  recorded; the measured difference is below pixel resolution, but it exists.
* Bad, because `snap` depends on the non-overlap assumption behind the
  coverage union. The fallback handles GEOS refusing; it cannot detect a
  subtly overlapping input that GEOS accepts. The validity check on the result
  narrows but does not close that gap.
* Neutral, because `validate` remains the default: nothing changes without
  opting in.

## Pros and Cons of the Options

### Two explicit methods, recorded per code

* Good, because it is fast where needed and identical where not.
* Good, because the choice is a recorded fact about each code, not a guess.
* Bad, because two paths are more to maintain than one.

### Replace the geometry path outright

* Good, because there is one path.
* Bad, because the 70 built codes would have to be rebuilt to be consistent,
  and until then the corpus would be mixed with no record of which is which.
* Bad, because it removes the ability to reproduce the original output.

### Keep the original path and wait

* Good, because nothing changes.
* Bad, because one code took more than eight hours with three larger ones
  queued; the corpus would take days, and any rebuild would too.

### Skip validation because silver validated

* Bad, because silver does not validate: there is no `make_valid`, `is_valid`
  or `buffer(0)` anywhere in silver or the readers, and 9.5% of sampled silver
  rows (1,895 of 19,869, across 69 of 120 files) are invalid with ring
  self-intersections. Unioning them would crash or produce wrong geometry.

## More Information

Superlinearity is per geometry, so the same remedy applies to any future
polygonised-raster source. Revisit if the fusion pipeline rasterises labels
directly onto its 30 arcsec grid: at that point a vector dissolve of
pixel-derived polygons is work that a raster union would do in a fraction of
the time, and gold's geometry could be simplified rather than sped up.
Related: ADR-0034 (gold v2 geometries).
