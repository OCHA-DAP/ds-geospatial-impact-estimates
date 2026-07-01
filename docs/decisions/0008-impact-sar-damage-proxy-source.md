---
status: "accepted"
date: 2026-06-28
deciders: zackarno
---

# Ingesting the IMPACT Initiatives SAR damage-proxy raster as a third source

## Context and Problem Statement

IMPACT Initiatives provided a preliminary 10 m Sentinel-1 SAR damage-proxy raster
(smoothed z-score > 0.7) covering ~8,400 km² across the impacted VE states — a
much larger footprint than the Microsoft/CEMS AOIs. It is a raster *proxy*, not a
vector per-building product, and it is masked to z > 0.7 (no values elsewhere).
How do we standardise it into the common model and surface it like the other
sources, given (a) it has no native "analysed area" layer and (b) ~3.7M of the
5M base buildings fall inside its extent?

## Decision Drivers

* Keep one comparable data model across sources (Microsoft, Copernicus EMS, this).
* Be honest about what the proxy is (screening, not confirmed damage).
* Don't break the (currently untiled) browser agreement view at 3.7M points.
* Ship something usable now; the proper version follows the tiling work.

## Decision Outcome

1. **Standardise the thresholds to the Copernicus `damage_class` model.** SAR
   pixels `0.7 ≤ z < 1.0` → *Possibly damaged* (class 1); `z ≥ 1.0` → *Damaged*
   (class 2). The grade carries SAR **confidence**, not severity (documented).
2. **Footprint = the raster's bounds** (later tightened to the validated S1 swath —
   see the Update below). The masked file has no built-up "analysed" layer, so the
   raster's extent *is* the footprint (nodata cells = nothing to extract there, not
   damage). Buildings inside the extent are SAR-analysed; `>0.7` cells are SAR-damaged.
3. **TEMPORARY — per-building projection is damaged-only.** Only SAR-*damaged*
   buildings enter the per-building / agreement layer (`building_flags`); the full
   ~3.7M analysed set is **not** materialised there, because the untiled
   deck.gl/agreement view and the single blob write cannot handle it. Admin-level
   facts (exposed / analysed / damaged / coverage) are still computed for SAR from
   the base, so the aggregate numbers are complete.

### Consequences

* Good: SAR slots into the existing comparison and map with minimal new
  machinery; aggregate (admin) stats are complete.
* **Bad / temporary:** the building-level agreement layer under-represents SAR
  (damaged-only). This is a stopgap and **MUST be rectified when PMTiles / vector
  tiling lands** (see the perf roadmap) — at which point all SAR-analysed
  buildings can be served. The damaged-only path is marked `# TEMPORARY` in
  `harmonize_common` / the SAR projection so it is easy to find and remove.
* Neutral: the raster bounds slightly overstate analysed *area* at the edges; the
  S1-swath clip (Update below) removes the masked SE single-swath edge and tightens
  the analysed-area figure. Building counts are unaffected.

## Update (2026-06-30): analysed extent = raster bounds ∩ the validated S1 swath

IMPACT later delivered the two Sentinel-1D **acquisition footprints** and noted the
proxy masks the single-swath southern/SE edge (footprint-aligned inflation). The
honest analysed extent is therefore the raster bounds **intersected with the
clipping swath** — the acquisition whose edge cuts through the box — keeping the NW
two-swath overlap (~69%) and dropping the masked SE single-swath triangle (~31% of
the box). This **supersedes the raster-bounds decision** in point 2 and resolves
revisit item (2) below. Implemented in `harmonize_impact_sar._analysed_extent`; the
bronze acquisition footprints are ingested by `pipelines/ingest_impact_sar_footprint.py`.

## More Information

The SAR layer is a hotspot/gap **screen**, not confirmed damage — side-looking
SAR anomalies can be debris, moisture, vegetation, or geometry. Always presented
with that caveat. Revisit (1) the damaged-only stopgap with the tiling work. Item
(2), the footprint, is resolved: IMPACT supplied the acquisition footprints and the
extent is now swath-clipped (see the Update above).
