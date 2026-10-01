---
status: "proposed"
date: 2026-09-25
deciders: Zack Arno
---

# One flood-label platinum over two golds, drawing water and flood separately

## Context and Problem Statement

Two flood-label corpora now exist on blob with different gold schemas: CEMS
gold v1 (ADR-0029: one flood `geometry` plus a valid mask, no `label_source`,
no `sensor_class`) and UNOSAT gold v2 (ADR-0034: `geom_water`, `geom_flood`,
`geom_possible`, `geom_valid`, `sensor_class`). The CEMS v2 rebuild ADR-0034
promised has not been written. The viewer is a way to catalogue events and
sense-check labels before the fusion work starts; the fusion work has not
started. How does one viewer show both corpora without a rebuild of either
gold, and without pretending the two say the same thing?

## Decision Drivers

* One page to catalogue all events, filterable by source, not two pages.
* No rebuild of either gold on the viewer's account: gold is the ML
  contract and its schema decisions (v2, the pending v3) are separate.
* What is drawn must be what the source mapped: CEMS never mapped water;
  many UNOSAT products never separated flood.
* A display product must be small; the golds are 9.8 GB and 3.6 GB.

## Considered Options

1. **One platinum catalog over both golds, with a thin harmonised display
   index and separate water / flood / mask collections.**
2. A second, UNOSAT-only page cloned from `pages/cems-flood-labels/`.
3. Rebuild CEMS gold to v2 first, then one platinum over one schema.

## Decision Outcome

Option 1. `pipelines/flood_labels/platinum.py` reads both golds per code, one
geometry column at a time, and writes four collections: `water` (UNOSAT
`geom_water`), `flood` (UNOSAT `geom_flood` where non-null and non-empty, plus
every CEMS extent), `valid-masks`, and `label-index` (the union of the two
indexes cut to the columns the page needs, with `label_source` on every row).
The page draws water and flood as separate toggleable layers, so a UNOSAT
"water here" is never rendered as "flood here", and a CEMS row simply has no
water layer.

Harmonisation is limited to what is derivable without a claim: the display
index carries CEMS `area_km2` as `flood_area_km2`, leaves `sensor_class` and
`water_area_km2` null for CEMS, resolves UNOSAT ISO3 country codes to HDX's
own dataset names, and unifies three country spellings through an explicit
alias table. Deriving `sensor_class` for CEMS from its sensor strings is left
for gold (ADR-0034's follow-up), not done in a display layer.

Geometry is simplified per source (1e-4° CEMS, 3e-4° UNOSAT, 5e-4° masks),
part by part, because GEOS's Douglas-Peucker on a whole MultiPolygon was
measured 140x slower than the same call over its exploded parts.

### Consequences

* Good: one catalog, one page, one token-issuer app; both corpora browsable
  from the first day without touching gold.
* Good: the page cannot misstate a source. Absent geometries are absent, and
  their counts are in `build_summary.json`.
* Bad: the display index is a third schema (thin, but a schema). It is
  explicitly display-only; the fusion reader must read gold.
* Bad: the viewer's `label-index` covers only the codes built; a code the
  builder skipped by flag is invisible there and visible only in the summary.
* Neutral: `pages/cems-flood-labels/` and its platinum stay until this page is
  confirmed; retiring them is a follow-up.

## Pros and Cons of the Options

### One platinum over both golds
* Good: no gold rebuild; matches the "catalogue all events" purpose.
* Bad: a small harmonisation layer to maintain (the alias table, the column
  mapping) until the golds converge.

### Separate UNOSAT page
* Good: fastest first look; no schema questions.
* Bad: two pages, two builders, two token apps, and the cross-source
  comparison the viewer exists for never happens on one screen.

### Rebuild CEMS gold to v2 first
* Good: one schema everywhere, no display harmonisation.
* Bad: blocks the viewer on a gold decision that is itself pending (ADR-0037
  proposes v3 rasters, which would make a v2 vector rebuild of CEMS wasted).

## More Information

Implementation: `src/gie/flood_labels/platinum.py`,
`pipelines/flood_labels/platinum.py`, `pages/flood-labels/`, the
`flood-labels` entry in `token-issuer/function_app.py`. Related: ADR-0029,
ADR-0034, ADR-0037, ADR-0022 (token issuer), ADR-0011 (client-side serving).
Revisit when CEMS gold is rebuilt (v2 or v3): the harmonisation layer should
then shrink to nothing.
