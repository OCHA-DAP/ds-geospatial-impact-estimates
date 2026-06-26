---
status: "accepted"
date: 2026-06-26
deciders: data science team
---

# Harmonize damage sources via an exposure base, an H3 grid, and a damage-fact table

## Context and Problem Statement

We receive damage data for the same disaster from multiple sources in
incommensurable forms: per-building damage labels on Microsoft/Google building
footprints (vector, point/polygon per building), Copernicus EMS damage
*polygons* not tied to any building (vector areas), and damage *rasters*
(per-pixel probability/class). Users want to aggregate all of it to OCHA COD
admin 0/1/2 units (and H3 cells) and **compare what each source says** for the
same unit.

The core problem is that the sources do not measure the same unit. "Microsoft
flags 600 buildings damaged" cannot be directly compared to "Copernicus maps
3.2 km² damaged" or "the raster mean damage probability is 0.4." Without a
deliberate reconciliation model, a source-comparison feature degrades into
unrelated numbers shown side by side.

## Decision Drivers

* Comparisons across sources must be apples-to-apples for at least one metric.
* New, unforeseen source formats must be addable without reshaping the store.
* Reporting geometry (admin levels, H3) will change/grow; ingestion must not be
  coupled to it.
* Emergency timeline: the model must be implementable in days, not weeks.

## Considered Options

1. **Exposure base + damage signals, harmonized on an H3 intermediate grid,
   served from a long damage-fact table** (admin as a reporting roll-up).
2. **Store each source in its native units**, compare side by side only.
3. **Aggregate each source directly to admin units**, no intermediate grid.

## Decision Outcome

Chosen option: **Option 1**. Two framing moves make heterogeneous sources
comparable and keep ingestion decoupled from reporting:

* **Exposure base vs damage signal.** Treat building footprints / population as
  the *exposure base* (the denominators — what is there). Treat each analysis as
  a *damage signal* (a label/area/raster claiming what is damaged). Footprint-
  linked sources join natively; non-linked sources (EMS polygons, rasters) are
  spatially joined onto the exposure base. This yields a genuinely comparable
  metric, e.g. "of N buildings in unit X, source A flags a, source B flags b."
* **H3 as the intermediate grid, admin as the reporting layer.** Every source —
  points, polygons, rasters — reduces to `(h3_index, metric, value)`. H3 → admin
  is then a cheap lookup, so adding an admin revision or H3 resolution does not
  re-process any source.

Both comparison modes the team asked for fall out of one store: **native units**
are distinct `metric` rows; the **common-base** comparison is an additional
`metric` computed against the exposure base.

The serving shape is a **long, narrow damage-fact table**:

```
source | method (model + version) | spatial_unit_type (h3 | adm0 | adm1 | adm2)
       | spatial_unit_id | metric | value | damage_class | imagery_date
       | confidence | ingested_at
```

Each source has a small **adapter** that emits rows in this schema; a new format
is a new adapter, not a schema change.

**Damage taxonomy.** Align `damage_class` to the **xBD / xView2 Joint Damage
Scale**: `0 no-damage, 1 minor, 2 major, 3 destroyed`. Carry the **Copernicus
EMS grading** as a parallel mapping rather than forcing it into the xBD scale,
since EMS grades are produced differently and a lossy cast would hide real
disagreement between sources.

### Consequences

* Good, because cross-source comparison has a defensible common metric.
* Good, because ingestion is decoupled from reporting geometry (admin/H3 churn
  is cheap).
* Good, because both "native units" and "common base" views come from one store.
* Bad, because non-linked sources require a spatial-join step with its own
  assumptions (e.g. a damage polygon intersecting a footprint = damaged), which
  must be documented per adapter and can introduce error.
* Bad, because the exposure base itself is a source with coverage gaps (missing
  footprints ⇒ undercount); the base choice is now a load-bearing decision.

## Pros and Cons of the Options

### Option 1 — exposure base + H3 + fact table

* Good, because it is the only option that makes incommensurable sources
  directly comparable.
* Good, because adapters isolate format-specific logic.
* Neutral, because it adds an H3 indexing step to every adapter.
* Bad, because it is more upfront modeling than dumping sources as-is.

### Option 2 — native units, side by side

* Good, because trivially fast to build.
* Bad, because "compare sources" never becomes a real comparison — just
  co-located, non-comparable numbers.

### Option 3 — aggregate directly to admin units

* Good, because fewer moving parts than an H3 layer.
* Bad, because every admin revision or new reporting geometry forces a full
  re-aggregation of all sources.
* Bad, because no source-agnostic intermediate makes re-aggregation to H3 or
  other grids expensive later.

## More Information

* xBD / xView2 Joint Damage Scale (0–3): https://arxiv.org/pdf/1911.09296
* Copernicus EMS rapid-mapping damage grading:
  https://mapping.emergency.copernicus.eu/about/rapid-mapping-manual/detection-methods-damage-assessment/
* Engine and storage choices that serve this model: see `0002`.
* Revisit if: a source cannot be meaningfully reduced to the exposure base
  (e.g. infrastructure damage with no building proxy), or if users need a metric
  the fact-table grain cannot express.
