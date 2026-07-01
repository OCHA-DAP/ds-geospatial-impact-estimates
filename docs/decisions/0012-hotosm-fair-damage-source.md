---
status: "accepted"
date: 2026-06-30
deciders: zackarno
---

# Adding the HOT fAIr building-damage assessment as a fifth source

## Context and Problem Statement

The Humanitarian OpenStreetMap Team's fAIr (AI-assisted mapping) produced a
building-damage assessment for the Venezuela earthquake, distributed on HDX
(dataset `venezuela-m-7-5-earthquake-building-damage-assessment`). It is a small
set of per-building damage **points** (128, in the La Guaira area), graded
minor / major / destroyed. Unlike IMPACT SAR (ADR-0008) and OSU (ADR-0009), it
ships **no analysed-area layer**. How do we standardise it into the common model
and surface it alongside the other sources?

## Decision Drivers

* Keep one comparable data model across sources (Microsoft, Copernicus EMS, IMPACT SAR, OSU, this).
* Reuse the per-source machinery (silver → `SOURCES` in `harmonize_common`) rather than inventing new.
* Be honest about what it is: a small, community/ML-derived detection set with no published coverage.
* Set it up so it becomes coverage-aware for free if fAIr later publishes an AOI.

## Considered Options

* **Snap the damage points to the Overture base** (as Copernicus EMS points are).
* **Project by id** (like OSU) — not possible: fAIr points are not Overture-keyed.

## Decision Outcome

1. **Snap fAIr damage points to the nearest Overture footprint (within 20 m).**
   The points are not keyed to Overture, so each is matched to its nearest base
   building within the same 20 m radius used for Copernicus EMS points (one point
   marks one building). This reuses the CEMS snap logic exactly.
2. **Map fAIr grades to the CEMS `damage_class` scale:** minor → 1 (Possibly),
   major → 2 (Damaged), destroyed → 3 (Destroyed), so it grades on the same axis
   as every other source.
3. **Detected-only: no analysed extent (yet).** fAIr published no coverage layer,
   so the source's analysed expression in `SOURCES` is `NULL`. As a result
   `analysed_buildings`, `coverage_fraction`, and `damaged_extrapolated` fall out
   NULL for HotOSM, leaving only `damaged_detected` meaningful. The viewer already
   renders detected-only sources (blank coverage/analysed, a "(point)" damaged
   count in the comparison hover). **When fAIr ships an AOI, swap the `NULL` for
   `sum(hot_analysed::INT)`** and it becomes coverage-aware like the rest — the hook
   is marked in `harmonize_common`.

### Consequences

* Good: the smallest, cheapest integration to date — a point-snap and a grade map,
  no new frontend logic; HotOSM appears as a fifth selectable source with the same hover.
* Good: a community / OSM-aligned, independently produced signal alongside the
  satellite and radar sources.
* **Limited by design:** with no AOI, HotOSM contributes a damaged *count* but no
  damage *fraction* or coverage. It confirms damage where fAIr looked, but cannot
  say what share of an area was assessed, so it reads as a detection overlay, not a
  rate. This is the `NULL` analysed expression, easy to flip later.
* Neutral: a small footprint now (128 points, La Guaira); it scales with whatever
  fAIr publishes next.

## More Information

fAIr is HOT's open, ML-assisted feature-detection tool, trained and validated with
the OpenStreetMap community; the damage set aligns to the OSM building base.
Ingest: `pipelines/ingest_hot_osm.py` (HDX CKAN → bronze GeoJSON, source `hot_osm`)
and `pipelines/harmonize_hot_osm.py` (→ silver `damage_points.parquet`). Revisit
when fAIr publishes an analysed AOI (flip to coverage-aware, per point 3) or a
larger detection set.
