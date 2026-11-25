---
status: "accepted"
date: 2026-07-14
deciders: Zack
---

# Viewer default-load latency: diagnosed, optimization deferred

## Context and Problem Statement

The staging viewer's initial load feels slow / "stuck on loading layers", even on
the default admin view with Buildings off. Investigated whether this was a cold
start, a LIST regression, or something broken. It is **none of those** — the load
completes (~9 s), the backend is warm (<0.3 s for `/api/sources` on a second
hit), and the default admin choropleth data itself is small (values parquet
164 KB, admin geometry 4 MB). This ADR records the finding and the decision to
defer the fix.

## Findings (measured, staging)

* The ~9 s is **many parallel requests contending on the single-worker backend**:
  CEMS `/api/coverage_detail` (~4 s), first-hit `/api/sources` (~2 s), and 9 ×
  `/api/extent` (fast individually — ~0.17 s — but ~1.6–3 s under full-page
  concurrency). Intermittent HTTP/2 / `ERR_ABORTED` errors to the dev blob
  occasionally make it *feel* stuck.
* The **buildings PMTiles is 51 MB (prod, no LIST) → 63 MB (staging, +LIST)** and
  ~7–10 s, but it loads **only when Buildings is toggled on** — a deliberate
  `z14`/no-drop tiling tradeoff (keeps sparse sources like DISHA visible).
* **LIST's marginal contribution:** one extra `/api/extent` request; its own
  extent is the slowest single one (~1.6 s, from the segmentized 2-scene union
  geometry); and +12 MB on the buildings tile. Not the primary cause.

## Considered Options (all deferred)

* **Don't gate the initial render on coverage overlays** — paint the choropleth
  immediately, load extent outlines + `coverage_detail` in the background.
  Highest UX win, LIST-agnostic, moderate change.
* **Simplify LIST's extent geometry** (coarser segmentize / `ST_Simplify`) — cuts
  its ~1.6 s. Small, LIST-specific.
* **More uvicorn workers** — removes single-worker contention. Systemic, but a
  deploy/infra change (memory/DuckDB implications).
* **Cache extent / coverage_detail responses** (static between data refreshes).
* **Buildings tile: zoom-gate or smarter tippecanoe dropping** — only relevant to
  the Buildings view.

## Decision Outcome

**Defer.** The load completes, is not a hard hang, is mostly pre-existing, and
LIST's share is marginal — not worth a perf refactor while the LIST source work
is being finished. Documented here so it isn't silently forgotten.

### Consequences

* Good — no scope creep onto a separate perf workstream; the levers are recorded.
* Bad — the ~9 s first load persists; may feel worse on slower networks.

## More Information

Revisit if the load is judged too slow in real use, when validating on the prod
tier / any CDN in front of it (behaviour may differ from the dev blob), or before
wider rollout. Best first step is the "don't gate render on overlays" option.
Related: ADR-0011 (PMTiles serving), ADR-0016 (tiered serving geometries),
ADR-0020 (LIST source).
