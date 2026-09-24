---
status: "proposed"
date: 2026-09-24
deciders: Zack Arno
---

# Gold v3 rasterises label sets onto the fusion grid instead of dissolving them

## Context and Problem Statement

Gold v2 (ADR-0034) dissolves each label set's polygons into one geometry per
class with `make_valid` and `union_all`. UNOSAT's polygons are polygonised
rasters — staircase outlines, hundreds of thousands of parts per feature,
millions of vertices in single geometries, pixel-corner self-intersections
(ADR-0036). GEOS noding is superlinear in vertices per geometry: one event
ran 13 h 58 min under v2's method and never finished; another took 6 h 19 min.
The `snap` method (ADR-0036) helps but is still a vector dissolve.

The sole consumer of these labels is the fusion model, built by the deciding
user, which reads labels as 30 arcsec cells (ds-flood-gfm spec: 1/120°,
EPSG:4326, integer row/col). Why dissolve in vector space at all?

## Decision Drivers

* Seconds per event, not hours; rebuildable on a laptop.
* The label semantics (area, acquisition interval, class per layer, coverage
  match, valid mask = footprint minus not-analysed) must be preserved exactly.
* One known consumer on one known grid; no requirement for resolution
  independence has been stated by anyone.

## Considered Options

1. **Rasterise directly**: burn each label set's contributing silver layers
   onto the 30 arcsec grid; union = OR, difference = AND NOT, no repair.
2. Keep dissolving, with `snap` (ADR-0036).
3. Dissolve in raster space at fine resolution (e.g. 10 m) then downsample.

## Decision Outcome

Chosen option 1, **proposed pending the proof of concept**
(`pipelines/unosat/gold_raster_poc.py`; acceptance: FL20220728NER and
FL20220418ZAF each under 60 s). A scanline rasteriser needs no validity, and
burning overlapping parts yields the same cells as burning their union, so
the three expensive GEOS steps disappear while the grouping — which is all of
gold's actual knowledge — stays identical.

### Consequences

* Good, because the dominant cost is removed rather than reduced.
* Good, because "0 = unobserved, not dry" is carried as an explicit valid band,
  exactly as the fusion spec requires.
* Bad, because exact vector areas are lost; areas become cell counts at 30
  arcsec. Stated in the index.
* Bad, because the archive is resolution-bound. Any future consumer at another
  resolution rasterises from silver (cheap) or unions (expensive) themselves.
  v2 remains available for that.
* Neutral, because v2 is not rebuilt or removed; ADR-0034 is superseded only
  for the fusion path.

## Pros and Cons of the Options

### Rasterise directly
* Good: seconds; no validity requirement; same grouping code.
* Bad: resolution-bound; approximate areas.

### Keep dissolving with `snap`
* Good: exact vector output, resolution independent.
* Bad: still hours on the worst events (FL20220728NER >1 h 35 min under snap
  and unfinished at time of writing); pays for resolution independence nobody
  has asked for.

### Fine raster then downsample
* Good: exact-ish areas.
* Bad: 10 m over a country is gigapixels per event; far more work than needed
  for a 30 arcsec target.

## More Information

Revisit if a second consumer needs vector labels or a different grid. Related:
ADR-0034 (v2 contract), ADR-0036 (why the dissolve is slow on this data).
