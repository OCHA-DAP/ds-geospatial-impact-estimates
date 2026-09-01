---
status: "proposed"
date: 2026-09-01
deciders: Zack Arno
---

# CEMS flood archive: corpus-level bronze plus era-normalized silver with per-polygon acquisition metadata

## Context and Problem Statement

We archived every CEMS Rapid Mapping flood vector package (2012 to present,
~2,900 zips) to build flood-extent training labels for ML. CEMS history spans
two portals and five naming/schema eras, and the imagery acquisition
datetime, which the labels cannot exist without, lives in a different place
per era (per-feature attributes, the portal API, or nowhere in the package).
How do we store and harmonize this so labels are usable and provenance
survives? Evidence: `exploratory/0005-cems-flood-feasibility/`.

## Decision Drivers

* Labels need per-polygon acquisition date/time; multiple images and
  digitizations exist per activation, product, and even polygon.
* Upstream demonstrably loses history (7 legacy activations already
  unavailable, 2 corrupted objects, 2 dead links).
* Five schema eras; any attribute mapping we write will contain mistakes.
* This is a general historical corpus, not event-scoped project data.

## Considered Options

* **Bronze**: (a) full original zips; (b) selective range-download of needed
  layers only (~10% of bytes); (c) extracted layers only, re-fetch on demand.
* **Keying**: (a) corpus layout in the `global` container keyed by
  activation code; (b) the repo's event-keyed `projects` layout.
* **Silver acquisition datetime**: (a) only exact values, drop the rest;
  (b) best available value per era with explicit precision/method columns;
  (c) delivery time as a proxy everywhere.
* **Era mapping**: (a) full canonical schema only; (b) thin canonical columns
  plus raw attributes preserved verbatim.

## Decision Outcome

Bronze = **full original zips** in `global/copernicus_ems/flood/bronze/`,
flat `code=EMSRnnn/` partitioning, with a transparency ledger (`_meta/`)
holding one row per target including explicitly-unavailable ones, per-zip
sha256 + member inventory, and an append-only transfer journal. Storage is
cheap (~31 GB); the zips are the insurance against upstream loss; flat
partitioning because legacy filenames resist reliable parsing, so parsed
metadata lives in the ledger where mistakes are one-line fixes.

Silver = three GeoParquet tables partitioned by code (`observed_event`,
`coverage`, `sources`), built only from bronze. Acquisition metadata is
**best-available-with-honesty**: `acq_datetime`/`acq_window_*` plus
`acq_precision` (minute | date | window) and `acq_method` (attribute | api |
api_window | window), so consumers filter to the precision they can tolerate
instead of receiving silently degraded dates. Era C/D (2017-23) starts as
event-to-delivery windows; a later catalog-matching stage (image footprint x
time window against Sentinel STAC, validated on EMSR574) can tighten those
without overwriting the conservative value. Canonical columns are thin;
every source attribute is preserved verbatim in `attrs_json`, so no era
mapping error is destructive. All monitorings/versions are kept (flood
evolution is signal), and `coverage` ships from day one because "no flood
polygon" is only interpretable next to "what was observed".

### Consequences

* Good: labels carry defensible provenance; re-harmonization never requires
  re-scraping CEMS; interrupted or wrong runs are recoverable from bronze.
* Bad: consumers must respect `acq_precision` (a naive reader could treat
  window mid-points as exact); two copies of the geometry exist (zip +
  parquet); the `products.parquet` ledger becomes a load-bearing interface.
* Rejected options, in short: selective download saved bandwidth we did not
  need and forfeited the archive insurance; event-keying does not fit 302
  activations with no `events.yaml` entries; exact-only acquisition dates
  would discard the 2017-23 era entirely; delivery-as-proxy would fabricate
  precision we do not have.
