---
status: "accepted"
date: 2026-07-01
deciders: zackarno
---

# CEMS damage display: native map keeps all coarse blocks; numbers use latest-only

## Context and Problem Statement

Copernicus EMS (activation EMSR884) grades built-up damage two ways: coarse
**area blocks** (`builtUpA`, the early estimate) and per-building **points**
(`builtUpP`, the detailed later update). Empirically, **each GRA product ships
exactly one grading layer** — area *or* point, never both (verified across all
delivered EMSR884 products, 2026-07-01). It is per-*product*, not per-monitoring
level: the initial (MONIT0) deliveries for the coastal/Caracas AOIs were coarse
areas and their MONIT1 updates were points-only, but Santa Cruz's initial
delivery was already points. Critically, **a monitoring update never re-ships the
coarse block** — a points-only MONIT1 carries no `builtUpA` layer.

So, across monitoring updates, how do we (a) aggregate the damage **numbers**
without double-counting the coarse block and the points for the same buildings,
and (b) **display** the source without silently erasing the coarse early-estimate
when a points-only update supersedes it?

## Decision Drivers

* Damage numbers must not double-count (coarse area + points of the same area).
* The map should never silently drop the earliest signal for an area — a
  points-only update may not cover the full footprint of the earlier coarse block.
* Keep one comparable model across sources (ADR-0001).

## Considered Options

1. **Latest-only everywhere** — filter both the numbers and the map to the latest
   product per AOI (`is_latest`).
2. **Keep-everything everywhere** — show and count every product's layers.
3. **Split (chosen)** — numbers latest-only; native map keeps *all* coarse blocks
   but only the latest points.

## Decision Outcome

Chosen: **Option 3.** Silver keeps every active product's grading, tagged
`layer_type` (area/point) and `is_latest` (latest monitoring per AOI).

* **Numbers** (gold → common model → choropleth + comparison): `WHERE is_latest`
  — the latest product per AOI only (points where available, else coarse areas).
  No double-counting; best-available estimate per AOI.
* **Native map — the exception:** the coarse **area** layer ignores `is_latest`
  and renders **all** blocks (translucent); the **point** layer renders
  `is_latest` only (solid). Because an update never re-ships the coarse block,
  retaining superseded blocks is the *only* way to keep the coarse early-estimate
  visible once a points-only update lands.

Option 1 rejected: a points-only update would erase the coarse blocks from the
map entirely (the update has no area layer to replace them), losing the early
estimate and any footprint the points don't cover. Option 2 rejected: it
double-counts the coarse block and the points for the same buildings.

### Consequences

* Good: numbers switch cleanly to the detailed points as they arrive, with no
  double-count; the coarse early estimate is never silently erased from the map.
* Good: robust to a later product whose footprint is smaller than the earlier
  coarse block — the block still holds that ground.
* **Bad / tradeoff:** for an AOI that received both a coarse MONIT0 and a point
  MONIT1, the native map shows **both** — translucent blocks *under* the solid
  points, over the same area — which can read as redundant/cluttered. First seen
  when all four coastal/Caracas AOIs doubled up (2026-07-01). Accepted as
  context-over-tidiness; revisit if it confuses users (e.g. a toggle, or hiding
  superseded blocks where the points fully cover them).
* Neutral: the "keep all coarse blocks" rule relies on the empirical fact that a
  product carries a single grading layer. If CEMS ever ships `builtUpA` **and**
  `builtUpP` in one product, revisit — the area layer's missing `is_latest`
  filter would then need reconsidering.

## More Information

Empirical basis (2026-07-01): every delivered EMSR884 GRA product carries exactly
one of `builtUpA`/`builtUpP`; the four MONIT1 updates were points-only. Code:
`harmonize_cems.build_silver` (keeps `layer_type` + `is_latest`), `build_gold`
(`WHERE is_latest`); `web/src/main.ts` `LAYER_SERVING.copernicus_ems` (area layer
has no `is_latest` filter, point layer filters `is_latest`). Related: the CEMS
coverage layer is a separate *display-layer* latest-only filter (coverage/cloud
show the latest acquisition only).
