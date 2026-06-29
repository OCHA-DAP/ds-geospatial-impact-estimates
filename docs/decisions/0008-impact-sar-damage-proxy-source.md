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
2. **Footprint = the raster's bounds.** The file is masked, so it has no built-up
   "analysed" layer; per the data owner the raster's true extent *is* the
   footprint (nodata cells = nothing to extract there, not damage). Buildings
   inside the extent are SAR-analysed; `>0.7` cells are SAR-damaged.
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
* Neutral: the bounds-as-footprint slightly overstates analysed *area* (includes
  some sea/edge), but building counts are unaffected (no buildings there).

## More Information

The SAR layer is a hotspot/gap **screen**, not confirmed damage — side-looking
SAR anomalies can be debris, moisture, vegetation, or geometry. Always presented
with that caveat. Revisit (1) the damaged-only stopgap with the tiling work, and
(2) the footprint if IMPACT supplies an explicit coverage layer.
