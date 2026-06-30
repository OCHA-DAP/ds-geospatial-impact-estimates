---
status: "accepted"
date: 2026-06-30
deciders: Zack (builds on Maxym's proposal, PR #4)
---

# v2 client-side serving — PMTiles + hyparquet on the existing App Service

## Context and Problem Statement

v1 serves every map layer as full GeoJSON/JSON from FastAPI (DuckDB-over-blob,
[0002](0002-duckdb-on-blob-v1-data-engine.md), [0004](0004-map-first-spa-fastapi.md)).
The heavy layers — Microsoft/Overture footprints, the per-source building points,
the admin/H3 choropleths — are multi-MB downloads, worst when *all* sources are
selected, and the deck.gl admin layer paints over the basemap labels. Maxym
proposed (PR #4) moving geometry to client-read **PMTiles** + values to
**hyparquet**, served from **Azure Static Web Apps + a Function + CDN**. IT has not
granted SWA/CDN/Function and gave no timeline. How do we get the client-side speed
win now, without waiting on infrastructure we don't control?

## Decision Drivers

* Speed: fetch only the viewport, not the whole dataset; cost scales with zoom, not data size.
* Don't block on IT (no SWA/CDN/Function ETA).
* Reuse the existing App Service + dev blob; additive, branch-isolated, no infra change.
* Preserve v1 UX exactly — especially the admin comparison-card hover.
* Per-layer, reversible migration — no big-bang rewrite.

## Considered Options

* **A — Wait for SWA + CDN + Function** (Maxym's full topology).
* **B — Adapt the same client-side serving onto the existing App Service now.**
* **C — Keep server-rendered GeoJSON, just put a CDN in front.**

## Decision Outcome

Chosen: **Option B**. We add a **platinum** serving tier in blob — PMTiles (Portolan
+ tippecanoe) with a STAC/versions catalog, plus a slim **values** parquet — and the
browser reads it **directly** from blob: range requests authorised by a read SAS from
a new `/api/token` endpoint, with CORS enabled on the account. The SPA uses an
explicit per-layer `LAYER_SERVING` registry (`pmtiles | deckgl`, **no silent
fallback**); converted layers render from MapLibre vector tiles, the rest stay on the
existing endpoints. Choropleth *values* are read in-browser with **hyparquet** from
`platinum/values/*.parquet` and joined to tile geometry via `setFeatureState`, so
v1's colouring + hover logic (`adminTip`) is reused verbatim. The SWA/CDN/Function
topology (Option A) becomes a later migration (see [roadmap](../roadmap.md)) — the
data tier is already in the shape it needs.

### Consequences

* Good — heavy GeoJSON fetches become viewport-streamed tiles; "all sources" is one shared tile; admin is a real MapLibre layer so labels render over it.
* Good — runs on today's infra; each layer flips independently; the data tier is forward-compatible with SWA/CDN.
* Good — values via hyparquet keep per-source/per-metric styling instant with no server round-trip.
* Bad — the read SAS is now **exposed to the browser** (in tile/parquet URLs). Acceptable for internal staging; must be hardened before any public exposure (see below).
* Bad — no deck.gl fallback by design; if blob/CORS/SAS breaks, a converted layer renders empty (the app still loads — the setups are guarded).
* Bad — platinum is another derived tier to keep in sync with gold (mitigated: aggregate tiles/values derive wholesale from gold; only native-geometry layers need per-source config).

### Security — SAS exposure & hardening

`/api/token` currently returns the app's configured **container-scoped, long-lived**
read SAS, so any app user could extract it and read the whole `projects` container.
Two hardening levers, **neither blocked by IT**:

1. **Scope to the project directory.** A flat blob SAS scopes only to one blob or a
   whole container, not an arbitrary prefix — but `imb0chd0dev` has **hierarchical
   namespace (ADLS Gen2)** enabled (confirmed: `isHnsEnabled=true`), so a
   **directory-scoped user-delegation SAS** can grant read to just
   `projects/ds-geospatial-impact-estimates/` — or, tighter, `…/platinum/` (all the
   browser needs) — exposing nothing else in the shared `projects` container. No
   dedicated container required.
2. **Short-lived, minted on demand.** Give the App Service a **managed identity** with
   *Storage Blob Data Reader* and have `/api/token` mint a **user-delegation SAS**
   (~15 min, scoped) per request — no stored key. This is Maxym's "Function mints the
   token," but the logic can live in the current FastAPI now and move to the Function
   under SWA later.

## Pros and Cons of the Options

### A — Wait for SWA + CDN + Function
* Good — the eventual end-state: global static hosting, edge-cached tiles, MI-minted scoped tokens.
* Bad — blocked on IT with no timeline; ships nothing now.

### B — Client-side serving on the existing App Service
* Good — ships the speed win now; data tier is forward-compatible with A.
* Neutral — still one origin (FastAPI serves the SPA + `/api/token` + unconverted layers).
* Bad — read SAS client-exposed until hardened; the pipeline tier (`build_platinum`) is a manual offline run.

### C — Server GeoJSON + CDN only
* Good — simplest; one config change.
* Bad — still ships whole-dataset payloads; doesn't fix the all-sources or admin-layering problems; caching a multi-MB GeoJSON ≠ viewport streaming.

## More Information

Builds on and realises Maxym's proposal (PR #4) — reconcile ADR numbering at merge.
Implementation: `pipelines/build_platinum.py` (Portolan + tippecanoe → `platinum/`,
slim values parquet; incremental via a persistent catalog), `web/src/main.ts`
(`LAYER_SERVING`/`OVERTURE_SERVING`/`ADMIN_SERVING` registries, `pmtiles` + `hyparquet`),
`api/main.py` (`/api/token`). Converted so far: native (Microsoft/CEMS/HotOSM), the
Overture buildings view, the admin choropleth. Deferred: H3, the agreement view, a
self-hosted PMTiles basemap. Revisit when SWA/CDN/Function land (see
[roadmap](../roadmap.md)), or before any public exposure — do the SAS hardening first.
