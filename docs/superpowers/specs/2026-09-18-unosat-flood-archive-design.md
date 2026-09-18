# UNOSAT flood archive: HDX corpus to shared flood-label gold

**Date:** 2026-09-18
**Status:** proposed (design discussion 2026-09-17 → 2026-09-18)
**Driver:** the flood-fusion work in `ds-flood-gfm` needs flood and water
extent labels outside Europe. The CEMS archive (ADR-0029) is 71 % European.
UNOSAT's satellite-detected water extents on HDX are the humanitarian
complement (South Sudan, Somalia, Madagascar, Sudan, Mozambique, Chad,
Bangladesh, Pakistan, Viet Nam) and must be archived, harmonized, and
published in a gold shape the fusion label reader can consume alongside CEMS.

## Decisions taken during design

- **Sibling of `pipelines/cems_flood/`, in this repo.** Reuses the ledger and
  journal shapes, the tuned `gie.blobio` uploader, the audit loop, and the
  `global`-container placement for historical corpora. Rejected: building it
  in `ds-flood-gfm` (re-implements the harvest plumbing).
- **All hazards to bronze, flood and cyclone to silver/gold.** Bronze is cheap
  after deduplication and UNOSAT damage assessments serve this repo's own
  purpose. Silver and gold are scoped by event-code prefix `FL` / `TC`.
- **Content-addressed bronze.** HDX datasets are cumulative snapshots: one
  South Sudan event appears in 35 datasets, each re-shipping the whole event
  zip. One bronze object per distinct sha256; ledger rows point at it.
- **Harvest SHP *and* GDB.** The GDB is not a duplicate: 2014–2019 layers store
  coded values (`Water_Class = 2`) whose lookup domains exist only in the GDB.
- **Water and flood kept apart from the start.** UNOSAT's `Water_Class` domain
  separates pre-flood water (0), flood water (1), possible flood-affected land
  (2, 3, 6), aquaculture (9) and cumulative maximum extent (99). Gold carries
  water and flood geometries as separate columns; cumulative layers are
  excluded from snapshot labels and counted.
- **Gold schema v2 shared with CEMS.** Adds `label_source` and per-kind
  geometries to the ADR-0029 two-table shape; CEMS gold is rebuilt to v2 in a
  follow-up so one reader serves both corpora.
- **Discovery via `hdx-python-api` (read-only).** Handles pagination, dataset
  dates and resource download headers. Rejected: hand-rolled CKAN calls (20
  lines, but re-implements what the maintained client already does). Kept
  thin: the ledger, not the client's objects, is the interface.

## Evidence (verified 2026-09-17/18)

| HDX UNOSAT corpus | count |
|---|---|
| datasets, all hazards | 1,465 |
| resources (SHP 621+, GDB 559+, XLSX 151, KMZ 15, GPKG 1) | 2,984 |
| nominal bytes, all resources (before dedup) | 75 GB (SHP 56, GDB 19) |
| distinct event codes parsed from resource names | 296 (`FL` 1,249 resources, `TC` 536, `CE` 333, `EQ` 221, other 173) |
| flood + cyclone event codes | 226 |
| event codes present in more than one HDX dataset | 204 (max 41 datasets for one code) |
| datasets with GDB but no SHP | 88 |
| resources whose name does not carry an event code | 16 % (almost all XLSX exposure tables) |

Five products sampled across 2015, 2017, 2019, 2022 and 2024 share one data
model: layer files `{SENSOR}_{YYYYMMDD}[_{YYYYMMDD}]_{Kind}_{Area}` (token
order varies: 2017 puts the area before the kind), and water layers carry
`Water_Clas`, `Water_Stat`, `Sensor_ID`, `Sensor_Dat` (per polygon),
`Confidence`, `Field_Vali`, `Notes`, `Area_m2`, `EventCode`, `StaffID`. Every
product ships an `AnalysisExtent`; optical products ship `CloudObstruction`;
2022+ products ship both `WaterExtent` and `FloodExtent` per acquisition; VIIRS
composites carry two dates (window). Older GDBs store domains `Water_Class`,
`Water_StatusID`, `Confidence_ID`, `Field_Validation`, and two sensor domains
(`Sensor_ID` legacy, `SensorID_v2`), readable via GDAL field domains and as
lookup tables.

## Out of scope

- UNOSAT products that are not on HDX (the unosat.org portal has older maps,
  mostly PDF). A later discovery source, not this spec.
- Damage-assessment silver (points, grading). Bronze only.
- The CEMS hydrography extension that gives CEMS water labels (own ADR).
- Rasterizing labels to the fusion grid (lives in `ds-flood-gfm`).

## Blob layout (container `global`, stage dev; `--stage prod` when promoting)

```
unosat/bronze/blob={sha256}/{original basename}        one object per distinct content
unosat/bronze/_meta/datasets.parquet                   HDX dataset metadata, all UNOSAT
unosat/bronze/_meta/resources.parquet                  THE LEDGER: one row per resource version
unosat/bronze/_meta/zip_contents.parquet               member inventory per sha256
unosat/bronze/_meta/transfers.jsonl                    append-only journal
unosat/bronze/_meta/domains.parquet                    coded-value domains harvested from GDBs
unosat/silver/{observed_event,coverage,sources}/code={EventCode}/data.parquet
unosat/silver/_meta/processing.parquet                 one row per (resource version, layer)
unosat/gold/label_index.parquet                        v2 schema (shared with CEMS)
unosat/gold/labels/code={EventCode}/data.parquet
```

## 1. Discovery (`discovery.py`)

Pull every dataset of HDX organisation `unosat` with `hdx-python-api` in
read-only mode (`user_agent="OCHA-CHD-DS unosat-archive"`). Write
`datasets.parquet` (dataset id, name, title, dataset_date, groups/countries,
tags, notes, methodology, metadata_created/modified) and the ledger
`resources.parquet`, one row per **resource version**:

`target_id` (= `{resource_id}@{last_modified}`), `dataset_id`, `dataset_name`,
`resource_id`, `resource_name`, `format`, `url`, `hdx_size`, `last_modified`,
`event_code` (regex `^([A-Z]{2})(\d{8})([A-Z]{3})` on the resource name, else
null), `hazard_prefix`, `iso3`, `scope` (`flood` for `FL`/`TC`, `other`, or
`unknown` when no code), `status`, `http_status`, `error`, `attempts`,
`attempted_at`, `uploaded_at`, `sha256`, `size_bytes`, `n_members`,
`missing_upstream`.

Statuses set here: `pending` (SHP, GDB, XLSX, GPKG), `excluded_kmz`. Re-running
merges onto the existing ledger exactly as CEMS: transfer outcomes survive, a
resource whose `last_modified` changed becomes a *new* row (new version, old
kept), vanished resources are flagged `missing_upstream`, never dropped.

## 2. Harvest (`harvest.py`)

For each `pending` row: download → `testzip` → inventory members → sha256 →
if `bronze/blob={sha256}/` already holds the basename with matching size,
record `uploaded_dedup` without uploading; else upload via `gie.blobio` →
verify size → record `uploaded`. Journal every attempt (success and failure)
in the `data_transfers.jsonl` record shape with origin URL and licence
(UNOSAT products on HDX: CC BY-IGO unless the dataset says otherwise; the
ledger records each dataset's stated licence).

Resume model as CEMS (ADR-0005): blob listing is truth; ledger rows claiming
`uploaded` whose object is missing are demoted loudly; checkpoints every 25
transfers and on exit. Failures stay visible; `--retry-failed` re-attempts.
Six workers by default (HDX is a shared public service; be polite).

After harvest, `domains.py` opens every GDB in bronze once (GDAL
`OpenFileGDB`, via the `ogrinfo -json` CLI or the Python bindings when
available) and writes `domains.parquet`: `(sha256, domain_name, code, value)`.
Domains are per-GDB because UNOSAT's own vocabulary drifted (two sensor
domains already seen).

## 3. Silver (`silver.py`)

Reads bronze only. Geometry and attributes come from the SHP resource; the
GDB is opened only for its domains, and as the geometry source for the 88
datasets that ship no SHP (`geometry_source` recorded per layer). Unit of
work: one distinct **layer content** — a layer is identified by
`(event_code, layer_name, sha256 of its .shp + .dbf members, or of the GDB
feature class exported to GeoParquet)`; the same layer re-shipped in 35 datasets is
processed once and the processing ledger lists every `target_id` that carried
it.

**Event code.** From the resource name; else from the layer's `EventCode`
attribute; else `HDX-{dataset_name}` with `code_method = dataset` flagged.

**Layer grammar.** Tokenise the layer name on `_`. Sensor = first token; dates
= 8-digit tokens (one → exact date, two → window); kind = the token matching
the vocabulary below; area = remaining tokens. Unmatched layers land in the
processing ledger as `unclassified` with their names, never silently dropped.

| kind tokens | table | role / layer_kind |
|---|---|---|
| `WaterExtent`, `SatelliteDetectedSurfaceWater`, `WaterAnalysis`, `Flood`, `Flood_Water` (2014 GDB) | observed_event | resolved per polygon from `Water_Class` (below) |
| `FloodExtent` | observed_event | `flood` |
| `AnalysisExtent`, `Extent`, `Analysis_Extent` | coverage | `footprint` |
| `CloudObstruction` | coverage | `not_analysed` |
| damage, IDP, shelter, landslide layers | skipped, counted by name in the processing ledger | |

**Per-polygon class.** `Water_Class` after domain resolution (text values
pass through; integer codes resolve via `domains.parquet` for that GDB, and
for SHP-only products via the SHP's own text or, failing that, the nearest
GDB of the same event code, with `class_method` recorded):

| class | `layer_kind` |
|---|---|
| Preflood Water (0) | `water_pre` |
| Flood Water (1), or any polygon from a `FloodExtent` layer | `flood` |
| Flood-Affected / Possible Flood Water (2, 3, 6) | `flood_possible` |
| Aquaculture (9), Tsunami-affected (14) | `other_water` |
| Maximum Flood Water Extent (Cumulative) (99) | `cumulative` (excluded from gold snapshots) |
| null | `water` (a WaterExtent layer without class = satellite-detected water) |

**Canonical columns on `observed_event`** (names shared with CEMS silver):
`code`, `code_method`, `target_ids` (list), `layer_name`, `layer_kind`, `area`
(UNOSAT area label), `sensor`, `acq_datetime`, `acq_window_start`,
`acq_window_end`, `acq_precision` (`date` | `window`; UNOSAT never gives
minutes), `acq_method` (`attribute` from `Sensor_Dat`; `filename` when only
the layer name carries the date; `window` for composites), `water_status`,
`confidence`, `field_validation`, `staff_id`, `notes`, `attrs_json`
(everything raw, verbatim), `geometry` (EPSG:4326). Filename date and
`Sensor_Dat` are cross-checked; disagreement sets `acq_conflict = true` and
keeps both values rather than picking one.

`coverage`: `code`, `layer_name`, `role` (`footprint` | `not_analysed`),
`sensor`, `acq_*` as above, `attrs_json`, `geometry`. `sources`: one row per
distinct `(code, sensor, acq_datetime)` seen across layers.

Processing ledger `silver/_meta/processing.parquet`: one row per (layer
content), with `status` ∈ {`ok`, `unclassified`, `skipped_non_water`,
`error`}, the carrying `target_ids`, polygon counts by `layer_kind`. Absence
of water polygons in a layer is `ok` with zero rows, never an error.

## 4. Gold (`gold.py`) — schema v2, shared with CEMS

Grain: one row per `(label_source, code, area, acq_start, acq_end)`. Per row
up to three dissolved geometries and one valid mask:

| column | content |
|---|---|
| `geom_water` | dissolve of `water`, `water_pre`, `flood` (all water present at acquisition); null if the product has no water layer |
| `geom_flood` | dissolve of `flood` polygons; null if not separable |
| `geom_possible` | dissolve of `flood_possible`; null if none |
| `geom_valid` | `footprint` for that acquisition minus `not_analysed`; `valid_basis` ∈ {`footprint_minus_cloud`, `footprint`, `none`} |

`label_index.parquet` (no geometry; the sampling catalogue) columns:
`label_source` (`unosat` | `cems`), `code`, `name`, `countries`, `aoi`
(UNOSAT area), `acq_start`, `acq_end`, `width_days`, `label_day`,
`acq_method`, `acq_precision`, `acq_conflict`, `sensor`, `sensor_gsd`
(null for UNOSAT), `det_methods` (null for UNOSAT), `product_classes`
(UNOSAT: layer kinds present), `confidence`, `water_status`, `n_polygons`,
`water_area_km2`, `flood_area_km2`, `possible_area_km2`, `valid_basis`,
`valid_area_km2`, `minx`, `miny`, `maxx`, `maxy`, `target_ids`,
`excluded_cumulative_n`. Areas in EPSG:6933 as CEMS gold does.

CEMS gold is rebuilt to v2 in a follow-up (`geom_flood` = today's geometry,
`geom_water` null until the hydrography extension lands, `label_source =
cems`). Until then the fusion reader in `ds-flood-gfm` accepts both v1 and v2
by column presence and says which it got.

## 5. Audit (`audit.py`) and report

Same defect-fix loop as CEMS (fix → audit → reprocess the stale list → audit
clean). Rules: **B1** no pending targets; **B2** blob census equals ledger
(sha256 set and sizes); **B3** every uploaded GDB has domain rows or an
explicit `no_domains` marker; **S1** processing ledger covers every uploaded
flood/cyclone resource version; **S2** every code with water layers has
`observed_event` and `coverage` partitions; **S3** acquisition dates plausible
(2005 ≤ year ≤ now) and within one year of the event-code date; **S4**
vocabularies within the documented sets; **S5** `unclassified` share per code
below a threshold, else listed; **G1** every gold row has `geom_valid` or
`valid_basis = none`; **G2** no `cumulative` polygons contribute to gold.
Exit 1 on failure; S/G failures land in the stale-code list.

`report.py` renders a status page (counts by year, country, sensor, precision,
kind) in the CEMS report template, plus a label-coverage map for the fusion
work (codes with `geom_water`, `geom_flood`, both).

## Fail-loud rules

Three states, never conflated: **upstream absence** (HDX 404, dataset without
resources) → explicit ledger status; **fetch or upload failure** → recorded,
raised at the end of the run, retried only on request; **empty content** (a
water layer with zero polygons, a code with no water layers) → `ok` rows with
zero counts. No `try/except: continue`; workers raise, the main thread records.

## Testing

`pytest` under `pipelines/unosat/tests/`: layer-grammar cases from the five
sampled products plus the 2014 GDB names; `Water_Class` resolution for text,
coded-with-domain, coded-without-domain (must raise or flag, never guess);
content deduplication (two ledger rows, one blob); acquisition cross-check
(agree, disagree, filename-only, window); gold dissolve with and without
cloud obstruction; v1/v2 gold reader compatibility. Fixtures are small
synthetic shapefiles and a trimmed GDB `ogrinfo -json` dump, not the sampled
zips.

## Phasing

1. **Grammar survey (spike, half a day).** Discovery + inventory of every zip's
   member names (no silver yet) → coverage of the layer grammar over all
   1,249 flood resources, list of unmatched names. Decides the vocabulary
   table above before any silver code is written.
2. Discovery + harvest + domains + audit B-rules. Harvest runs unattended.
3. Silver + audit S-rules + processing ledger.
4. Gold v2 + report + audit G-rules; fusion reader in `ds-flood-gfm` updated.
5. Follow-ups, each its own ADR: CEMS gold v2 rebuild; CEMS hydrography
   extraction; unosat.org non-HDX products.

## ADRs to write with this work

- `0033-unosat-flood-archive-content-addressed-bronze.md` — HDX cumulative
  snapshots → sha256-keyed bronze; SHP+GDB both archived because of domains.
- `0034-flood-label-gold-v2-water-and-flood-geometries.md` — shared gold with
  `label_source` and separate water / flood / possible geometries; supersedes
  the gold section of ADR-0029.

## Open questions

- HDX rate limits for ~3,000 downloads: none documented; six workers with
  back-off, watch for 429.
- Whether `hdx-python-api` needs a config file even in read-only mode
  (settle in phase 1).
- 2019 Somalia layers show `EventCode` attribute disagreeing with the resource
  name code (FL20191010SOM inside FL20191030SOM). Treat the resource name as
  primary and record the attribute; confirm in the grammar survey.
