---
status: "proposed"
date: 2026-06-29
deciders: data science team
---

# v2 serving: PMTiles + hyparquet + exceljs client-side, Portolan catalog, short-lived SAS

## Context and Problem Statement

The v1 serving layer (ADRs 0002–0004, 0007) runs DuckDB server-side on an App
Service, converts GeoParquet geometry via `ST_AsWKB` → GeoPandas → GeoJSON on
every request, and authenticates to blob with long-lived SAS tokens (rotated
manually, inspectable in app settings). This has three compounding problems:

1. **Geometry is over-served.** All admin boundaries and native source polygons
   are downloaded to the browser as complete GeoJSON collections regardless of
   zoom or viewport. For large native layers (Microsoft footprints, CEMS damage
   polygons) this is multi-MB payloads per source per session.
2. **Auth is a rotation burden.** A leaked or stale long-lived SAS surfaces as
   mid-session auth failures and requires operator intervention to rotate.
3. **The server is load-bearing for data.** All analytical queries, geometry
   transformations, and workbook generation block on the App Service process.
   The `lru_cache` is the only protection against redundant work and is lost on
   restart.

A redesign is viable now because: (a) hyparquet enables efficient columnar reads
of GeoParquet from the browser without a query engine; (b) PMTiles enables
streaming only the visible viewport tiles directly from blob; (c) exceljs builds
styled multi-sheet workbooks in the browser; and (d) Portolan manages the PMTiles
build, catalog versioning, and push lifecycle in the pipeline — including
pre-generating H3 hexagon polygon geometry so the browser needs no geometry
library at all.

## Decision Drivers

* Browser downloads only the geometry and data it actually renders.
* No long-lived secrets stored in app settings.
* The pipeline — not the server — owns all data transformation.
* The server is reduced to a single stateless concern: token vending.
* Drop every dependency that is no longer justified: GeoPandas, deck.gl,
  DuckDB server-side, openpyxl.
* Portolan's catalog lifecycle (versioning, sync, PMTiles generation) replaces
  ad-hoc blob writes from pipelines.

## Considered Options

1. **v2: PMTiles (Portolan) + hyparquet + exceljs client-side + short-lived SAS** (this ADR)
2. **Managed identity upgrade only** — switch `db.py` to `credential_chain`; keep
   server-side DuckDB and GeoJSON serving unchanged.
3. **DuckDB WASM** — move the full SQL query engine to the browser; keep GeoJSON
   wire format.

## Decision Outcome

Chosen option: **Option 1**. Portolan becomes the pipeline step that converts
silver/gold GeoParquet into a versioned, cloud-native catalog with PMTiles
derivatives — including pre-generated H3 hexagon polygons — and pushes
everything to blob. The browser fetches a short-lived (24 h) SAS from a thin
token-vending endpoint, then reads all data directly from blob: geometry via
native MapLibre + PMTiles, analytics via hyparquet, workbook export via exceljs.
The App Service is replaced by a static host (blob + CDN or Azure Static Web
Apps) plus a single lightweight Azure Function for token vending.

Managed identity (Option 2) solves auth but leaves geometry over-serving and
server compute unchanged. DuckDB WASM (Option 3) requires a ~25 MB bundle with
WASM warm-up latency, still needs JOIN logic for geometry + metrics, and does
not solve the geometry serving problem without PMTiles work anyway.

### What the pipeline gains

Each event/country pipeline run ends with a Portolan step:

```bash
portolan add admin-boundaries/ --pmtiles   # adm1/2/3 from CODAB bronze
portolan add h3-hexagons/      --pmtiles   # H3 polygon geometry pre-generated
portolan add source-extents/   --pmtiles   # per-source analysed_extent
portolan add native-geometry/  --pmtiles   # MS footprints + CEMS damage polys
portolan add coverage-detail/  --pmtiles   # CEMS AOI + not-analysed gaps
portolan push                              # sync changed collections to blob
```

H3 hexagon polygon geometry is pre-generated in the pipeline using DuckDB's
`h3_cell_to_boundary(unit_id)` before Portolan builds the PMTiles. The browser
never needs to compute or hold a geometry library for H3 — it renders the tiles
like any other MapLibre vector layer.

PMTiles embed the feature properties needed for map styling at tile-build time
(`damaged`, `ems_grade`, `damage_class`, `adm{n}_id`, `aoi_name`, etc.) so the
browser needs no attribute join for rendering. Damage metrics (which change per
source selection) are fetched separately via hyparquet and joined client-side via
MapLibre `setFeatureState` using stable CODAB pcodes as feature IDs.

Gold analytics tables (`facts.parquet`, `building_flags.parquet`) remain plain
GeoParquet on blob. No Portolan management is needed for them — they are the
read target for hyparquet.

Portolan's `versions.json` per collection is the authoritative record of what is
live on blob, with checksums and version history. When a new CEMS product lands,
only the changed collections are re-pushed.

### What the browser does

1. On load: `GET /api/token` → receives a 24 h SAS for the dev blob account.
2. **Admin choropleth**: hyparquet reads `gold/model=common/adm0=VE/facts.parquet`
   (column-pruned: `unit_id`, `unit_type`, `source`, `metric`, `value`), pivots
   metrics in JS. MapLibre loads the admin PMTiles; `setFeatureState` joins
   damage values by pcode. Rendered as a native MapLibre fill layer.
3. **H3 layer**: hyparquet reads the same `facts.parquet`, filters `unit_type='h3'`.
   MapLibre loads the pre-generated H3 PMTiles; `setFeatureState` joins metrics
   by H3 index. Rendered as a native MapLibre fill layer.
4. **Native geometry**: MapLibre loads MS footprint / CEMS damage PMTiles.
   Styling is driven by MapLibre paint expressions referencing tile-embedded
   properties (`damaged`, `ems_grade`, `damage_class`) — no `setFeatureState`
   or data join needed. Native MapLibre fill layer.
5. **Buildings / agreement**: hyparquet reads `building_flags.parquet` (columns:
   `lon`, `lat`, `ms_dmg`, `ms_analysed`, `cems_dmg`, `cems_analysed`). Rendered
   as a native MapLibre circle layer.
6. **Coverage extents + CEMS detail**: PMTiles, MapLibre line/fill layers, hover
   via `queryRenderedFeatures`.
7. **Export**: exceljs builds the styled multi-sheet workbook in the browser
   from the same hyparquet reads used for the map, with no server round-trip.
   exceljs is preferred over SheetJS: SheetJS Community Edition (used in
   `hdx-cod-ab-geocoder`) deliberately omits cell styling in its free tier —
   fills, fonts, and borders require SheetJS Pro (paid). Our workbook requires
   green header fills, bold white fonts, zebra striping, freeze panes, and
   number formats, so only exceljs is viable. exceljs is MIT-licensed but has
   not had a meaningful release since October 2023; this is an acceptable risk
   for a stable, bounded problem.

### What is deleted

| Deleted | Replacement |
| ------- | ----------- |
| `src/gie/serving.py` | Logic moves to browser (hyparquet) and pipeline (Portolan) |
| `src/gie/db.py`, `src/gie/config.py` serving paths | No server-side DB reads remain |
| All `/api/common/*`, `/api/buildings`, `/api/native`, `/api/extent`, `/api/coverage_detail`, `/api/agreement`, `/api/export.xlsx` endpoints | hyparquet + PMTiles + exceljs direct in browser |
| `ST_AsWKB` → GeoPandas → `.to_json()` conversion | PMTiles at pipeline time |
| Long-lived `DSCI_AZ_BLOB_DEV_SAS` app setting | Short-lived SAS from `/api/token` |
| GeoPandas, openpyxl dependencies | Removed from server entirely |
| `azure` DuckDB extension + `certifi` TLS workaround (ADR-0007 gotcha) | Removed |
| deck.gl (`GeoJsonLayer`, `H3HexagonLayer`, `ScatterplotLayer`, `MapboxOverlay`) | Native MapLibre layers throughout |
| App Service (Linux P0v3) | Azure Static Web Apps + single Azure Function |

### What stays

| Kept | Reason |
| ---- | ------ |
| `/api/token` (Azure Function) | Storage account key never goes to the browser |
| SPA (Vite build) | Hosted on Azure Static Web Apps or blob + CDN |
| Gold/silver Parquet pipeline | Unchanged — Portolan step is additive |

### One-time infrastructure change

CORS must be configured on the blob storage account to allow browser range
requests:

```text
Allowed origins:  <app domain>
Allowed methods:  GET, HEAD
Allowed headers:  Range, x-ms-*
Exposed headers:  Accept-Ranges, Content-Range, Content-Length
```

This is a one-time storage account config, not a code change.

### Consequences

* Good, because geometry is viewport-streamed — only visible tiles are
  downloaded, regardless of dataset size.
* Good, because the long-lived SAS is removed from app settings; 24 h expiry
  limits blast radius without manual rotation.
* Good, because the App Service is eliminated entirely — the server is one
  stateless Azure Function and a static file host.
* Good, because GeoPandas, openpyxl, DuckDB, and the `azure` extension leave
  the deploy; cold-start time and image complexity drop to near zero.
* Good, because deck.gl is removed — the frontend depends only on MapLibre,
  reducing bundle size and eliminating the `MapboxOverlay` interleaving
  complexity.
* Good, because H3 hexagon geometry is pre-computed in the pipeline, removing
  any need for a geometry library in the browser.
* Good, because Portolan's `versions.json` gives an explicit, checksummed record
  of what is live, replacing implicit "whatever the pipeline last wrote."
* Bad, because the choropleth and H3 rendering changes from deck.gl data-driven
  layers to MapLibre `setFeatureState`. This is a genuine rewrite of the map
  rendering layer.
* Bad, because PMTiles must be regenerated whenever silver geometry changes (new
  CEMS product, updated CODAB boundaries). Portolan's push only syncs changed
  collections, but the build step still runs.
* Bad, because the SAS token handed to the browser appears in network logs and
  browser memory. Acceptable for non-sensitive humanitarian data on dev blob;
  revisit before serving sensitive or production data.

## Pros and Cons of the Options

### Option 1 — PMTiles + hyparquet + exceljs + Portolan + short-lived SAS (chosen)

* Good, because each concern is handled by the right layer: pipeline owns
  transformation, browser owns rendering and export, Function owns auth.
* Good, because Portolan brings catalog structure, versioning, and a standard
  push/sync workflow to what was previously ad-hoc blob writes.
* Good, because the infrastructure footprint is minimal — no persistent compute.
* Bad, because it is the largest surface-area change: map rendering, pipeline,
  auth, server, and export all change together.

### Option 2 — Managed identity upgrade only

* Good, because it is a one-function `db.py` change + one role grant.
* Bad, because the full-dataset GeoJSON download problem remains.
* Bad, because server compute cost and dependency footprint are unchanged.
* Neutral, because this remains available as a component of Option 1: the
  Function can use managed identity to generate user-delegation SAS tokens
  without holding a storage account key.

### Option 3 — DuckDB WASM

* Good, because it preserves the SQL query pattern from `serving.py`.
* Bad, because the WASM bundle is ~25 MB with a warm-up cost.
* Bad, because JOINs between gold facts and CODAB boundaries still run in the
  browser on every session.
* Bad, because it does not solve the geometry serving problem without PMTiles
  work anyway.

## More Information

* Portolan CLI: `portolan add --pmtiles` generates PMTiles using DuckDB spatial
  or tippecanoe as fallback. The H3 pipeline step uses `h3_cell_to_boundary()`
  before handing geometry to Portolan.
* hyparquet: pure-JS Parquet reader with HTTP range request support; no WASM,
  ~50 KB. `https://github.com/hyparam/hyparquet`
* exceljs: MIT-licensed client-side Excel builder with full styling support
  (fills, fonts, freeze panes, number formats, auto-filter). Unmaintained since
  October 2023 but stable for this bounded use case. SheetJS Community Edition
  was considered but rejected: styling requires SheetJS Pro (paid tier).
  `https://github.com/exceljs/exceljs`
* `setFeatureState` vs `setFilter`: use `setFeatureState` only where damage
  metrics are joined dynamically (choropleth, H3). For native geometry layers
  where all styling attributes (`damaged`, `ems_grade`, `damage_class`) are
  embedded in tiles at build time, use MapLibre paint expressions directly —
  no join required. Pattern validated in `hdx-cod-ab-geocoder`.
* MapLibre `setFeatureState`: stable pcode/H3 index feature IDs must be promoted
  in the PMTiles build (`--feature-id adm3_id` or equivalent in Portolan).
* If managed identity is granted, the Function can issue user-delegation SAS
  tokens via `DefaultAzureCredential` — no storage account key stored anywhere.
* **Future (post-stable): service worker caching.** PMTiles and GeoParquet files
  on blob are immutable between Portolan pushes, so re-downloading them on every
  session is wasteful. A service worker can cache them keyed on the blob path
  with the SAS query string stripped — so token rotation doesn't bust the cache
  — and evict on version change by checking Portolan's `versions.json`. Validated
  by `fieldmaps/topo-tools` (version-key eviction for WASM binaries) and
  `hdx-cod-ab-geocoder` (offline toggle with full binary caching). Deferred
  until the v2 architecture is stable: service workers add meaningful operational
  complexity and are hard to debug during active development.
