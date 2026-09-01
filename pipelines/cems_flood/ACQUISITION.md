# CEMS flood archive — data acquisition & provenance

This document specifies exactly where the data comes from, endpoint by
endpoint, how it was transferred, and how every transfer is verified and
recorded. Companion docs: [`README.md`](README.md) (operations, storage
layout, resume semantics) and
`exploratory/0005-cems-flood-feasibility/findings.md` (the source-mapping
evidence this design is based on).

## What the corpus is

All vector damage/delineation packages published by the **Copernicus
Emergency Management Service (CEMS) Rapid Mapping** for **flood activations,
2012 → present** (302 activations, EMSR009–EMSR927 at time of harvest),
archived byte-identical to Azure blob (`global/copernicus_ems/flood/bronze/`)
together with a complete transfer ledger.

**Licence:** CEMS products are free for re-use with attribution
(© European Union, Copernicus Emergency Management Service). Recorded on
every transfer record.

## Data sources — every endpoint

CEMS publishes through **two generations of portal**; both are public, no
authentication. The only access requirement is a browser-like `User-Agent`
header (the default `python-requests` UA receives HTTP 403 from the
new-portal backend). All requests are plain HTTPS `GET`.

### 1. Archive portal (`mapping.emergency.copernicus.eu`) — full history

| Purpose | Endpoint | Interface |
|---|---|---|
| Activation inventory (all 1,060 CEMS activations, 2012→) | `https://mapping.emergency.copernicus.eu/activations/api/activations/?format=json&limit=…&offset=…` | REST API (Django REST Framework), paginated JSON |
| Product listing per legacy activation (EMSR001–655) | `https://mapping.emergency.copernicus.eu/activations/{EMSRnnn}/` | Server-rendered HTML; product cards parsed (AOI tabs → title, delivery timestamp, download links) |
| Legacy product files | `https://cems-mapping-website.s3.eu-west-1.amazonaws.com/static/activations/{EMSRnnn}/{filename}_vector.zip` | Direct S3 object GET (links taken verbatim from the page above) |

The activation-inventory API is the **authoritative activation list**: it
covers the full history, including activations the newer portal does not
serve. Flood activations are selected by its `category.slug == "flood"`
field. `EMSN*` codes (the separate Risk & Recovery Mapping service) are out
of scope.

### 2. Rapid Mapping portal (`rapidmapping.emergency.copernicus.eu`) — EMSR656+ (Mar 2023 →)

Accessed via the team-standard [`ocha-lens`](https://github.com/OCHA-DAP/ocha-lens)
package (`ocha_lens.cems`), which wraps:

| Purpose | Endpoint | Interface |
|---|---|---|
| Activation list | `https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations-info/` | JSON, paginated |
| Activation detail (AOIs → products → layers/images, incl. per-image `acquisitionTime`) | `https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code={EMSRnnn}` | JSON |
| Product files | `https://rapidmapping.emergency.copernicus.eu/backend/{EMSRnnn}/AOI{nn}/{PRODUCT}/{filename}.zip` → HTTP 302 → presigned `https://rapidmapping.s3.amazonaws.com/…` | S3 object GET via redirect |

The two sources overlap for EMSR656+; discovery **cross-validates them and
fails loudly on any disagreement** (they agreed exactly at harvest time).

### What is deliberately not used

- The old portal `emergency.copernicus.eu/mapping/…` — decommissioned
  (pages 404; only Wayback Machine captures remain).
- New-portal per-layer endpoints (vector tiles / COGs) — map-display formats,
  not suitable for bulk vector extraction.
- Map PDFs/JPEGs and Reference (pre-event) map packages — out of scope for
  the flood-extent corpus; Reference packages are still inventoried in the
  ledger (`excluded_ref`) for completeness.

## Scope of the download

Per activation, every **Delineation (DEL), First Estimate (FEP) and Grading
(GRA)** *vector package* (zip of shapefiles + GeoJSON/KMZ/XLSX/XML sidecars),
including every AOI, every monitoring iteration and every version — 2,888
packages (~20 GB). Packages are stored **byte-identical** to what CEMS
serves; no re-compression or modification.

## Acquisition method

Two-stage, ledger-driven design (`discovery.py` → `harvest.py`):

1. **Discovery** enumerates every target from the endpoints above into a
   ledger (`products.parquet`) — one row per product zip **including rows
   for products that cannot be fetched**, each with an explicit reason
   (never migrated to the archive portal; closed without delivery; no
   published URL). Re-running discovery merges: transfer outcomes are
   preserved, new targets are added, vanished targets are flagged, never
   deleted.
2. **Harvest** transfers each pending target:
   `download → HTTP status check → zip integrity check (ZipFile.testzip) →
   member inventory → sha256 → chunked upload to blob → post-upload size
   verification → journal record`. Transfers run in a small thread pool
   (default 6); the blob store is the source of truth for resume, so an
   interrupted run continues exactly where it stopped, and blobs found
   without ledger metadata are re-hashed and re-inventoried from the blob
   copy (corrupt copies are demoted and re-transferred).

Politeness: serial page crawl with delays during discovery; bounded
concurrency against S3 during harvest; retry with exponential backoff on
transient HTTP 429/5xx.

## Verification & transparency artifacts

Everything lands beside the data in `…/bronze/_meta/`:

| File | Contents |
|---|---|
| `activations.parquet` | all flood activations, both portals, cross-validated |
| `products.parquet` | the ledger: one row per target — status, source URL, blob path, sha256, size, timestamps, HTTP status/error for failures |
| `zip_contents.parquet` | one row per file **inside** every archived zip (name, size, compressed size), built during download |
| `transfers.jsonl` | append-only journal of every attempt (success or failure), with provider, licence, origin URL, sha256 |

Failure statuses are permanent ledger rows, retried only explicitly. Known
upstream defects found during the harvest (recorded with evidence, out of
our control): a handful of legacy activations whose products were never
migrated to the archive portal; two archive S3 objects that contain an HTML
page instead of the advertised zip; two new-portal URLs that 404 despite
being advertised by the portal's own manifest.

## Processing status

This corpus is the **bronze** (raw archive) layer only. Planned downstream
(silver) processing — flood-extent layer extraction across the five CEMS
naming eras, canonical schema, and imagery **acquisition-datetime**
enrichment (native attributes for 2012–16; the portal API for 2023+;
footprint × time-window Sentinel catalog matching for 2017–23) — is
specified in `exploratory/0005-cems-flood-feasibility/findings.md` and will
be documented separately when built.

## Reproducing / updating

```sh
uv run --group etl --group api python pipelines/cems_flood/discovery.py   # refresh ledger (backfill)
uv run --group etl --group api python pipelines/cems_flood/harvest.py     # transfer anything new
uv run --group etl --group api python pipelines/cems_flood/report.py      # regenerate status report
```
