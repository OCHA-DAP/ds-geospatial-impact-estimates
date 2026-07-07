---
status: "proposed"
date: 2026-07-07
deciders:
---

# Native footprint serving: per-source tiles vs. a unified assessed-footprint tile (and whether to tile the Overture base)

> **PROPOSAL ONLY — no decision has been made.** This records an architectural
> question we keep running into so it isn't lost; it does not choose an option.
> Nothing here changes current behaviour.

## Context and Problem Statement

The viewer's "native data" view serves each source's own damage geometry as its
own PMTiles collection (`platinum/native-<source>/…`): Microsoft footprints, CEMS
grade polygons/points, UH graded footprints, and now IMPACT SAR + OSU footprints.

Most of these footprints **are the Overture base** we already hold:

* **OSU** — 100% (every building is `overture_id`-keyed).
* **IMPACT SAR v2** — ~84% (13,433 of 81,437 are blank-id "national-source"
  footprints Overture lacks; the rest are Overture).
* **Microsoft, UH** — effectively Overture geometry (their own near-identical copies).

So the per-source native tiles **duplicate the same building polygons** several times
over. This surfaced while wiring UH (footprint dedup) and IMPACT/OSU (their footprints
are Overture), and it is the same underlying question as **"should we just tile the
Overture base once?"** — because the natural dedup is exactly that: one base-footprint
tile, with each source reduced to a flag on it. It also feeds the SWA migration goal
(ADR-0011 Phase 3) of serving everything from static PMTiles.

## Decision Drivers

* Avoid storing the same geometry N times (blob storage, tile-build time).
* Keep the "native footprint" view (polygons, not centroid points).
* All-PMTiles / static serving for the SWA cutover.
* Client performance (a native view must stay responsive).
* Cover **all** source shapes, not just Overture-footprint ones.

## Considered Options

* **A. Status quo — per-source native footprint tiles.** What we do today.
* **B. Unified assessed-footprint tile + per-source flags.** Tile the assessed
  Overture buildings once as polygons (like today's `building_flags`, but polygons
  instead of centroid points), carrying every source's flag/grade as attributes;
  the native view colours that one tile by the selected source. Non-Overture
  geometry (IMPACT's 13k national footprints, and the non-footprint sources) still
  needs its own layer.
* **C. Shared points tile only.** Drop per-source native footprints; use the
  existing `building_flags` points tile for every native view. Full dedup, but
  points, not footprints (already rejected in-thread — a downgrade for the view).
* **D. Hybrid.** Unified tile (B) for the Overture-footprint sources; keep
  per-source tiles for the exceptions (CEMS grades, HotOSM/DISHA points, UNEP
  debris GBA footprints, IMPACT national footprints).

## Decision Outcome

**None yet — proposed.** The current per-source tiles (A) stay in place; they are
consistent, working, and SWA-friendly, and the duplication costs storage, not
correctness (a client only ever loads the one selected source's tile). This ADR
exists to hold the question for the Phase-3 SWA effort, not to resolve it.

Open questions to settle before choosing:

* **Gold geometry cost.** `building_flags` is centroid *points* precisely because the
  full base was too heavy for one blob write; option B revives that size problem
  (now as a tile, not a single parquet — needs measuring).
* **Client scale.** The admin choropleth colours ~12k units by feature-state cheaply;
  doing the same over ~565k+ assessed buildings (or millions of base buildings) is a
  different order and may not perform — needs a spike.
* **Coverage.** B/D only dedup the Overture-footprint sources. CEMS (grade areas +
  points), HotOSM/DISHA (points), UNEP debris (GBA footprints), and IMPACT's 13k
  national footprints do not fit and still need their own geometry.
* **Is the win worth it?** Current native tiles are ~5–25 MB each; total duplication
  is modest. Measure the actual storage/latency before refactoring gold + platinum +
  viewer.

## Pros and Cons of the Options

### A. Per-source tiles (current)
* Good — simple, consistent, already works; each tile is independent and static.
* Good — handles every source shape uniformly.
* Bad — duplicates Overture geometry across sources.

### B. Unified assessed-footprint tile
* Good — one geometry copy; the real dedup; native = "colour the base by a source".
* Bad — needs gold to carry footprint geometry (size problem) and a viewer rework.
* Bad — feature-state at building scale is unproven; may not perform.
* Bad — doesn't cover non-Overture-footprint sources on its own.

### C. Shared points tile
* Good — maximum dedup, one tile, no new work (it exists).
* Bad — points, not footprints — a worse native view (rejected in-thread).

### D. Hybrid
* Good — dedups the common case, keeps the exceptions working.
* Bad — two native-render paths to maintain; most of B's costs, partial benefit.

## More Information

Relates to ADR-0011 (client-side PMTiles serving, Phase 3 = SWA), ADR-0009 (OSU
id-join over geometry), ADR-0015 (IMPACT v2 footprints are ~Overture), and the UH
work (ADR-0018, exploratory/0004). Revisit as part of the SWA migration; a small
spike on gold-geometry tile size + building-scale feature-state performance should
precede any decision.
