---
status: "accepted"
date: 2026-07-02
deciders: zackarno
supersedes: 0008-impact-sar-damage-proxy-source
---

# Switch the IMPACT SAR damage source from the v1 raster proxy to the v2 vector product

## Context and Problem Statement

IMPACT Initiatives delivered a **v2** damage product for the VE earthquake: a vector
GeoPackage of **damaged building footprints** plus an **analysed-area polygon**,
replacing the v1 10 m Sentinel-1 SAR-proxy *raster* (ADR-0008). The method is
unchanged — a backscatter *amplitude* anomaly (a wide-area screen, not confirmed
damage; not coherence, that is OSU) — but v2 has already intersected the proxy with
the **common Overture building base**, keeping a building when the proxy covers
**≥50%** of its footprint. That makes it per-building and directly comparable to the
OSU / Microsoft / CEMS products. The analyst reports it as a considerable
improvement over v1 in scale and quality (checked against VHR imagery and
statistical testing). Do we adopt it and supersede v1?

## Decision Drivers

* Comparability: per-building on the shared Overture base (the common model,
  ADR-0001), instead of a raster we sample ourselves.
* Wider, better coverage: a 32,712 km² AOI that **fully envelops** v1's ~8,400 km²,
  plus analyst-reported quality gains.
* Clean supersede with no coverage regression, and preserved provenance + caveat.

## Considered Options

* Ingest v2 as a new vector adapter, keying on its geometry, and supersede v1.
* Ingest v2 but attach damage by an **id-join** onto our Overture base (as OSU does).
* Keep the v1 raster proxy.

## Decision Outcome

Chosen: **ingest v2 as a new, additive vector adapter and supersede v1.**

1. **Bronze** — `ingest_impact_v2.py` lands the two v2 GeoPackages as received (via
   the `blobio` chunked uploader). The v1 raster bronze is kept for provenance.
2. **Silver** — `harmonize_impact_v2.py` writes `building_damage.parquet` +
   `analysed_extent.parquet` (the v2 AOI), **replacing** the raster-derived
   `impact_initiatives` silver. Damaged-only, one "likely damaged/destroyed" class →
   `damage_class = 2` (as OSU); the affected fraction `b_aff_sf`/`bdg_sfc` is carried
   as the confidence signal.
3. **Extend the shared base, and flag impact by geometry (not an id-join).** To keep
   the ~25k out-of-base buildings, we (a) **generalised the Overture pull trigger**
   (`ingest_overture._affected_adm1_bboxes`) to union **every** source's
   `analysed_extent` and clip each pull to the state polygon — so a re-run fetched
   the v2 states (only new areas; +6 states, ~2.6M buildings), and (b) flag a base
   building damaged when it **contains a v2 footprint's centroid** — a 1:1 match (v2
   footprints *are* Overture geometry) that needs no id, so it catches the 13,433
   blank-id national footprints an id-join would drop. The silver carries geometry
   precisely to enable this join.
4. **Additive** — `ingest_impact_sar.py` / `harmonize_impact_sar.py` stay for
   provenance, unused. The method is unchanged, so ADR-0008's amplitude-proxy caveat
   ("wide-area screen, not confirmed damage") still travels downstream.

Verification: [`exploratory/0002-impact-v2-assessment`](../../exploratory/0002-impact-v2-assessment/findings.md).

### Consequences

* Good: per-building, comparable, wider AOI, clean supersede. Extending the base was
  **cheap and by-design** — the trigger already derives states from coverage and
  skips ones already pulled.
* It also **fixed a latent gap**: the trigger previously watched only CEMS+Microsoft,
  so it had silently dropped ~0.6% of OSU (Portuguesa/Trujillo). Now every source
  keeps the base complete over its assessed area (see ADR-0006 note).
* Why not the pure id-join: v2's Overture `id` is **blank for 13,433 national-source
  footprints**, and ~30% of the AOI was in states we hadn't pulled — an id-join would
  silently drop ~25k of the 81,437 buildings.
* Neutral: the impact silver gains a geometry column vs OSU's id-keyed pattern, and
  `harmonize_common` flags impact by **centroid-containment** onto the base (not the
  id-join). Centroid, not `ST_Intersects`, to avoid edge-neighbour over-flag
  (~86k → the product's 81,437).
* Bad / open: the delivery's `class`/`subtype` fields are garbled (unused here; flag
  to IMPACT). Still a proxy screen, not confirmed damage — unchanged from v1.

## Pros and Cons of the Options

### Pure id-join onto our Overture base (like OSU)
Simplest, matches OSU. But drops the ~13,433 blank-id national footprints and every
building in states we hadn't pulled Overture for (~25k total) — unacceptable for a
product whose whole point is wider coverage. Rejected.

### Extend the base + geometry-flag (chosen)
Extend the base via the existing pull trigger and flag impact by geometry. Early on
this looked like "a large, unnecessary pull", but the trigger already derives states
from coverage, skips ones already present, and clips to the state polygon — so it is
cheap and the *designed* path, not a hack. It also repairs the OSU gap. This is what
we did.

### Keep the v1 raster proxy
Narrower (~8,400 km²), not per-building, less comparable; the analyst confirms v2 is
the better product. Rejected.
