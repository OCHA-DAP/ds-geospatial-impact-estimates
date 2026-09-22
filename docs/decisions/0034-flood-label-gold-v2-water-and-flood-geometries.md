---
status: "proposed"
date: 2026-09-22
deciders: Zack Arno
---

# Flood-label gold v2: one schema for two corpora, with water and flood as separate geometries

## Context and Problem Statement

Gold v1 (built for the CEMS flood archive under ADR-0029) is two tables: a
geometry-free `label_index.parquet` to filter and stratify on, and one
GeoParquet payload per code carrying, per label set, a single dissolved flood
`geometry` plus a `valid_geometry` mask. It says nothing about which corpus a
row came from, and it has exactly one label geometry.

The UNOSAT archive breaks both assumptions. UNOSAT ships permanent and
pre-flood water, flood water, possible flood-affected land and cumulative
maxima as separate layers and per-polygon classes; 1,829 of its label layers
are VIIRS at 375 m while others are Pléiades digitisations. The flood-fusion
work in `ds-flood-gfm` needs **water extent at acquisition** as its primary
target — the quantity a SAR or optical sensor actually observes and the only
one comparable across sources — and the flood increment where a source
separated it. Meanwhile the fusion label reader has to consume CEMS and
UNOSAT together. What shape do the two corpora publish?

## Decision Drivers

* The fusion target is observed water; flood is a derived, source-dependent
  subset. A schema with one geometry forces one of the two to be discarded.
* "No flood here" and "this source never separated flood" must not render
  identically, or a training set silently acquires false negatives.
* One reader for both corpora, or every consumer re-implements the join.
* A consumer must be able to tier a 375 m automated product apart from a
  hand-digitised VHR one.
* Nothing may be dropped silently: excluded polygons have to be counted.

## Considered Options

* Gold v2: one schema for both corpora, with per-kind geometries
* Flood-only gold (keep v1's single geometry, drop water)
* Per-source gold schemas, joined by the consumer

## Decision Outcome

Chosen option: **gold v2 shared by both corpora**. One row per
`(label_source, code, area_label, acq_start, acq_end)` carrying `geom_water`
(the dissolve of `water`, `water_pre` and `flood` — everything wet at
acquisition), `geom_flood` (the dissolve of `flood` alone), `geom_possible`
and the `geom_valid` mask, with `label_source` ∈ {`unosat`, `cems`} and
`sensor_class` ∈ {`sar`, `optical_vhr`, `optical_hr`, `optical_coarse`,
`multiple`, `unknown`} on the index — `multiple` whenever the contributing
rows carry more than one distinct sensor, so a set built from two instruments
is never tiered as though one produced it. `aggregate_max`, `aggregate_min` and
`other_water` never enter a geometry and are counted in
`excluded_aggregate_n`. CEMS gold is rebuilt to v2 in a follow-up
(`geom_flood` = today's `geometry`, `geom_valid` = today's `valid_geometry`,
`geom_water` null until the hydrography extension lands).

Three nullability rules carry most of the meaning:

* `geom_flood` is **null** where no layer in the label set set out to map
  flood extent (a `WaterExtent` layer with no per-polygon class says "water
  here", not "flood here"), and an **empty geometry** where a flood layer
  looked and found none. Unknown and zero are different states.
* `geom_valid` is the matched footprint minus what was not analysed, with
  `valid_basis` ∈ {`footprint_minus_cloud`, `footprint`, `none`}. Coverage is
  matched to a label set **by shared source product (`target_id`) and same
  area**, following the precedent CEMS gold set, with the acquisition interval
  kept as a refinement recorded in `valid_match` ∈ {`interval`, `product`}
  rather than as a gate. A footprint from another area never stands in; `none`
  is the honest answer there.
* A label set whose every polygon was an excluded kind keeps its row, with
  null geometries and `excluded_aggregate_n` set, rather than vanishing.

### Consequences

* Good, because the fusion work gets its water target without losing the
  flood increment, and can tell a missing label from a negative one.
* Good, because one reader serves both corpora and `label_source` makes the
  provenance of every row explicit in the data rather than in the file path.
* Good, because the exclusions are visible per label set instead of being an
  unexplained gap between a silver polygon count and a gold one.
* Good, because matching coverage the way CEMS gold does — by source product,
  not by acquisition interval — is what makes the mask exist at all for most
  of the archive. Measured on the real silver output (285 label sets, 185
  footprint rows): exact `(area, interval)` matching yields a mask for 46 % of
  sets, interval overlap 51 %, product-and-area 73 %. Two layers out of one
  product rarely share an interval exactly, because a footprint layer usually
  carries only its filename's date while the observed layer's per-polygon
  sensor dates widen its interval.
* Bad, because `target_id` alone would reach 84 % and we deliberately leave
  those 11 points on the table: they are a neighbouring AOI's footprint
  masking this one, which is the precise claim the mask exists to prevent.
  `valid_match` is what lets a consumer decide how much to trust the rest.
* Bad, because the labels file now has four geometry columns, which needs
  GeoParquet multi-geometry support (geopandas ≥ 1.0) and a reader that asks
  for the column it wants rather than `.geometry`.
* Bad, because CEMS gold has to be rebuilt; until it is, the fusion reader
  accepts v1 by column presence and reports which version it got.

## Pros and Cons of the Options

### Gold v2: one schema for both corpora, with per-kind geometries

* Good, because water and flood are both preserved, per source, per
  acquisition.
* Good, because `sensor_class` lets a consumer weight a VIIRS label
  differently from a Pléiades one without parsing sensor strings.
* Neutral, because the wider schema costs little: three of the four geometry
  columns are null or small for most rows.
* Bad, because it obliges a CEMS rebuild to keep one reader true.

### Flood-only gold (keep v1's single geometry)

* Good, because nothing changes and CEMS needs no rebuild.
* Bad, because it discards the water target the fusion spec chose, which is
  the one thing every sensor actually observes.
* Bad, because UNOSAT's `WaterExtent` layers — the bulk of several countries'
  coverage — would have no representable label at all, or would be silently
  filed as flood, which is a fabricated claim.

### Per-source gold schemas, joined by the consumer

* Good, because each corpus keeps whatever shape suits it, with no rebuild.
* Bad, because every consumer then writes the harmonisation we chose to own,
  and each one writes it slightly differently.
* Bad, because divergence is invisible: nothing fails when the two schemas
  drift, the training set just quietly means something else.

## More Information

Supersedes the gold shape recorded in
[ADR-0029](0029-cems-flood-archive-and-silver-schema.md) (CEMS flood archive);
the silver decisions there stand. The coverage-matching rule follows that
archive's own precedent — CEMS gold selects a label set's coverage with
`cov[cov.target_id.isin(tids)]` — rather than inventing a second rule. Implementation: `src/gie/unosat/gold.py` and
`pipelines/unosat/gold.py`; spec §4 of
`docs/superpowers/specs/2026-09-18-unosat-flood-archive-design.md` is the
authority on the column list. Revisit when CEMS gold is rebuilt to v2, and
again if a third corpus needs a `layer_kind` v2 does not carry.
