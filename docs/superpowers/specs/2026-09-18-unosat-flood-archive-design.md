# UNOSAT flood archive: HDX corpus to shared flood-label gold

**Date:** 2026-09-18 (revised the same day after a full-corpus survey)
**Status:** proposed (design discussion 2026-09-17 → 2026-09-18)
**Driver:** the flood-fusion work in `ds-flood-gfm` needs flood and water
extent labels outside Europe. The CEMS archive (ADR-0029) is 71 % European.
UNOSAT's satellite-detected water extents catalogued on HDX are the
humanitarian complement (South Sudan, Somalia, Madagascar, Sudan, Mozambique,
Chad, Bangladesh, Pakistan, Viet Nam) and must be archived, harmonized, and
published in a gold shape the fusion label reader can consume alongside CEMS.

## Decisions taken during design

- **Sibling of `pipelines/cems_flood/`, in this repo.** Reuses the ledger and
  journal shapes, the tuned `gie.blobio` uploader, the audit loop, and the
  `global`-container placement for historical corpora. Rejected: building it
  in `ds-flood-gfm` (re-implements the harvest plumbing).
- **All hazards to bronze, flood and cyclone to silver/gold.** Bronze is cheap
  after deduplication and UNOSAT damage assessments serve this repo's own
  purpose. Silver and gold are scoped by event-code prefix `FL` / `TC`.
- **HDX is the catalogue, not the store.** Resource URLs point at five hosts
  (`unosat.org` 984, `unosat-maps.web.cern.ch` 436, `cern.ch` 109,
  `data.humdata.org` 11, `floods.unosat.org` 1). All support HTTP range
  requests. Availability is UNOSAT's, not HDX's: 6 advertised zips are not
  zips and 19 URLs 404 (backslash-encoded paths, a bare `.shp`, a "Kml
  Link" suffix, and plainly missing files; the 404s were stable across
  retries hours apart). These are ledger statuses, not retries.
- **Content-addressed bronze.** HDX datasets are cumulative snapshots: 515 of
  1,516 zips are byte-for-byte identical in member set and sizes to another
  zip; one South Sudan event appears in 35 datasets. One bronze object per
  distinct sha256; ledger rows point at it.
- **Harvest SHP *and* GDB, and silver reads the GDB first.** Where a dataset
  ships both, the GDB is a superset (South Sudan: 196 feature classes vs 138
  shapefiles), carries typed dates and full field names (the SHP truncates
  to `Water_Clas`, `Sensor_Dat`, `EventCod`), binds every coded field to its
  domain, and is authoritative where the two disagree (the SHP export of one
  South Sudan layer carries a Bangladesh event code; the GDB carries the
  right one). SHP is the fallback for the 88 datasets without a GDB and the
  cross-check everywhere else.
- **Water, pre-flood water and flood kept apart from the start.** UNOSAT ships
  `PermanentWater` / `PreFloodWaterExtent` layers (1,423 in the corpus),
  `FloodExtent` (2,010), `WaterExtent` (1,049) and cumulative
  `MaximumFloodWaterExtent` (1,443), and its `Water_Class` domains separate
  pre-flood water, flood water, possible flood-affected land and cumulative
  extents per polygon. Gold carries water and flood geometries as separate
  columns; aggregate layers are excluded from snapshot labels and counted.
- **Gold schema v2 shared with CEMS.** Adds `label_source`, per-kind
  geometries and a sensor class to the ADR-0029 two-table shape; CEMS gold is
  rebuilt to v2 in a follow-up so one reader serves both corpora.
- **Discovery via `hdx-python-api` (read-only).** Verified: no config file
  needed with `Configuration.create(hdx_read_only=True)`; resources expose
  `id`, `url`, `download_url`, `last_modified`, `size` and `hash` (populated
  on 402 of 408 recent resources). Rejected: hand-rolled CKAN calls.

## Evidence (verified 2026-09-17/18)

Full HDX metadata pull, remote central-directory inventory of all 1,541 SHP,
GDB and GPKG resources (1,516 readable), and 43 full zips downloaded across
2015–2026 plus one 196-layer geodatabase.

| HDX UNOSAT corpus | count |
|---|---|
| datasets, all hazards | 1,465 |
| resources (SHP 621+, GDB 559+, XLSX 151, KMZ 15, GPKG 1) | 2,984 |
| licences (dataset level) | cc-by-sa 1,119, hdx-other 321, cc-by 23, cc-by-igo 2 |
| bytes: distinct URLs / distinct content / flood+cyclone distinct content | 29.6 GB / 22.3 GB / 19.7 GB (uncompressed members total 124 GB) |
| silver working set (GDB where present, SHP only where not) | 7.6 GB, 410 zips |
| zips identical in content to another zip | 515 of 1,516 |
| zip members appearing in more than one zip | 28,451 of 81,937 |
| distinct event codes parsed from resource names | 296 (`FL` 1,249 resources, `TC` 536, `CE` 333, `EQ` 221, other 173) |
| flood + cyclone event codes | 226 |
| event codes present in more than one HDX dataset | 204 (max 41) |
| datasets with GDB but no SHP | 88 |
| unavailable upstream (not a zip / 404) | 6 / 19 |
| measured on the full run 2026-09-18 (ledger rows, not URLs) | `corrupt_upstream` 6, `unavailable_404` 48, dead host `floods.unosat.org` 13, malformed `ttps://` URLs 2 |

Layer grammar over the 11,842 flood/cyclone shapefile layers (2,600 distinct
names): 96 % classify by name into water, pre-flood water, flood, aggregate,
footprint, not-analysed or a skip class (damage, IDP, infrastructure,
landslide); the 445 unmatched are impact layers (Kherson harbours,
affected buildings, health facilities). Sensor tokens: VIIRS 1,829, S2 516,
S1 396, ST1 299 (a Sentinel-1 alias), PHR 206, WV3 188, ST2/ST3 229, and a
long tail. Dates: 94 % of layers carrying both a filename date and a
per-polygon sensor date agree or fall inside the filename window; the rest
are month/day transpositions and a few days' drift. Two layers were
EPSG:32636, not 4326.

## Out of scope

- UNOSAT products not on HDX (the unosat.org portal has older maps, mostly
  PDF). A later discovery source.
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
unosat/bronze/_meta/domains.parquet                    (sha256, layer, field, domain, code, value) from every GDB
unosat/silver/{observed_event,coverage}/code={EventCode}/layer={content_hash}-{name8}.parquet
unosat/silver/sources/code={EventCode}/data.parquet
unosat/silver/_meta/{layers,layers_status}.parquet     layer inventory per (sha256, layer)
unosat/silver/_meta/processing.parquet                 one row per (sha256, layer)
unosat/gold/label_index.parquet                        v2 schema (shared with CEMS)
unosat/gold/labels/code={EventCode}/data.parquet
```

A missing local work dir is bootstrapped from this `_meta/` copy before any
CLI reads a local file, so the blob copy is always the recoverable baseline
for the ledger, journal and domains bookkeeping.

## 1. Discovery (`discovery.py`)

Pull every dataset of HDX organisation `unosat` with `hdx-python-api`
(`hdx_read_only=True`, `user_agent="OCHA-CHD-DS unosat-archive"`). Write
`datasets.parquet` (dataset id, name, title, dataset_date, groups/countries,
tags, licence, notes, methodology, metadata_created/modified) and the ledger
`resources.parquet`, one row per **resource version**:

`target_id` (= `{resource_id}@{last_modified}`), `dataset_id`, `dataset_name`,
`resource_id`, `resource_name`, `format`, `url`, `host`, `hdx_size`,
`hdx_hash`, `last_modified`, `event_code` (regex `^([A-Z]{2})(\d{8})([A-Z]{3})`
on the resource name, else null), `hazard_prefix`, `iso3`, `scope` (`flood`
for `FL`/`TC`, `other`, or `unknown` when no code), `status`, `http_status`,
`error`, `attempts`, `attempted_at`, `uploaded_at`, `sha256`, `size_bytes`,
`n_members`, `missing_upstream`.

Statuses set here: `pending` (SHP, GDB, XLSX, GPKG), `excluded_format`. Re-running
merges onto the existing ledger exactly as CEMS: transfer outcomes survive, a
resource whose `last_modified` or `hdx_hash` changed becomes a *new* row (new
version, old kept), vanished resources are flagged `missing_upstream`, never
dropped.

## 2. Harvest (`harvest.py`)

For each `pending` row: download → `testzip` → inventory members → sha256 →
if `bronze/blob={sha256}/` already holds the basename with matching size,
record `uploaded_dedup` without uploading; else upload via `gie.blobio` →
verify size → record `uploaded`. The downloaded file is kept in the local
cache (§2b). Journal every attempt in the
`data_transfers.jsonl` record shape with origin URL, host and the dataset's
stated licence. Terminal upstream states are explicit statuses:
`unavailable_404`, `corrupt_upstream` (HTTP 200 but not a zip). A valid zip whose
members use a compression method Python cannot test (seen: one such file on
the first full run) is archived anyway — bytes hashed, members listed — with
status `uploaded_untested`, so the untestable state is visible, not a crash.

**Download once per URL.** The same zip URL is listed under many HDX datasets
(2,925 pending rows map to 1,721 distinct URLs). One representative row per URL
is fetched; its outcome, sha256, size and member inventory are propagated to
the sibling rows sharing that URL (journaled as `via_url_sibling`), and rows
whose URL already has an uploaded row are settled as `uploaded_dedup` before
any download. Neither is
retried by `--retry-failed`; both stay in the ledger.

Resume model as CEMS (ADR-0005): blob listing is truth; ledger rows claiming
`uploaded` whose object is missing are demoted loudly; checkpoints every 25
transfers and on exit. Six workers by default, per-host back-off on 429/503.

`domains.py` opens every GDB in bronze once (GDAL `OpenFileGDB` via
`ogrinfo -json`, since the venv has no `osgeo`) and writes `domains.parquet`
with one row per `(sha256, layer, field, domain_name, code, value)`. The
binding is **per layer and field**, not per GDB: the same GDB binds
`Water_Class` on older layers and `Water_Class2` on newer ones, and two sensor
domains coexist (`Sensor_ID` legacy, `SensorID_v2`; VIIRS-NOAA = 53,
Sentinel-1 = 42, Sentinel-2 = 44, Pleiades = 35, "Combination of Sensors" =
999).

## 2b. Local cache and download model

**Cache.** A local mirror of the bronze layout, `{cache_dir}/unosat/bronze/
blob={sha256}/{basename}`, with `cache_dir` from `GIE_CACHE_DIR` or
`platformdirs.user_cache_dir("gie")`. Because paths are content-addressed the
cache is never stale: a file exists at its hash path or it does not. Harvest
writes through (it holds the bytes to test and hash them anyway); silver
reads through (local path, else fetch from blob and keep). Blob is the source
of truth; the cache is disposable; `--no-cache` disables it. Budget ~8 GB for the
silver working set, ~22 GB if the whole bronze is mirrored.

Rejected: `pooch` (static registry of names and hashes; our ledger is the
registry and the corpus is discovered dynamically), `fsspec` `filecache::`
(caches by URL; redundant once paths are content-addressed), DVC (a second
content-addressed store beside the ledger and blob machinery already here).

**Download model.** Thread pool, six workers, as `cems_flood/harvest.py`
(twelve broke uploads on a home uplink). Asyncio is rejected: the ceiling is
politeness and uplink, not Python, and each item does CPU work (zip test,
hash, inventory) that does not belong on an event loop. Differences from
CEMS: stream to disk (a 337 MB zip exists in the corpus), hash while
streaming in one pass, and a per-host concurrency cap with back-off since
five hosts share the pool. External copiers (rclone) are rejected because
per-file verification into the ledger is the point.

## 3. Silver (`silver.py`)

Reads bronze only. **Source preference per dataset version: GDB, then SHP.**
Both are inventoried; when both exist the SHP is read only to cross-check
layer presence and decoded text (`d_*` columns, present in some exports), and
disagreements are recorded per layer (`shp_gdb_mismatch`). `geometry_source`
∈ {`gdb`, `shp`} on every row. Geometry is reprojected to EPSG:4326 when the
source is not (seen: EPSG:32636); the source CRS is recorded.

**The layer inventory decides what a zip is, not the HDX `format` label**, and
the GDB-first preference is applied to that. The same content is sometimes
listed as `Geodatabase` in one dataset and `SHP` in others
(`FL20140910PAK_gdb.zip`); trusting the label made silver look for `.shp`
members inside a geodatabase. The label rides along as `format_label` with a
`format_mismatch` flag, so the HDX metadata defect stays visible rather than
being quietly corrected. A geodatabase entry `ogrinfo` reports with no
geometry field is one of the coded-value lookup tables (`Water_Class`,
`Water_StatusID`, …), not a feature class: `skipped_non_water`, never read.
The same null geometry type on a shapefile member means only that the
inventory records none, so that layer is read and its geometry decides.

**Unit of work** is one distinct **layer content**: `(event_code, layer_name,
content hash)` where the content hash is the sha256 of the `.shp`+`.dbf`
members or of the GDB feature class exported to GeoParquet. A layer re-shipped
in 35 datasets is processed once; the processing ledger lists every
`target_id` that carried it.

**Storage: one file per layer content and name**,
`{observed_event,coverage}/code={EventCode}/layer={content_hash}-{name8}.parquet`
(`name8` = first 8 hex of `sha256(layer_name)`), not one `data.parquet` per
code. The key is the file name, so a re-shipped layer lands on a path that
already exists and the write is skipped — the pass is idempotent and
deduplicates by construction rather than by rewriting a whole code partition
from an accumulated in-memory list, which a partial or resumed run would
silently truncate. The layer name is part of the key because identical
geometry under two names is real and meaningful (the same analysis footprint
shipped for two acquisition dates); hashing content alone collapsed such
layers onto one path and dropped the second. `sources` stays one
`data.parquet` per code (it is a small per-code summary, not layer content).

**Local mirror first, blob in the background.** Every file is written to
`{work_dir}/silver/…` — the same relative layout — and uploaded from there by
a small thread pool with a short socket timeout (60 s, against bronze's 300 s:
the median upload is 0.5 s and observed stalls ran to 470 s and made up half a
real run's wall time). The processing ledger's `uploaded` flag says whether
that push is confirmed; a checkpoint drains the in-flight uploads first, so a
persisted row never claims an upload that is still in the air, and a killed
run leaves `uploaded=False` rows whose files are already built and need only
pushing. `uploaded` null (a ledger written before the flag existed) is
reconciled against the blob listing, not assumed either way. The mirror is
disposable: blob is the truth, and gold reads through
`silver.iter_layer_files`, which fetches whatever the mirror lacks. Zips are
processed in parallel worker processes (`--workers`, default 3) by the pure
`silver.process_unit`; the ledger, the uploads and the printing stay on the
main thread.

Note for readers of these files: they live under a `code={EventCode}/`
directory *and* carry a `code` column, so pyarrow's hive-partition inference
collides with the data. Read them with `silver.read_layer_file`, which turns
that inference off.

**One partition per content.** A content listed under two event codes (an
ISO3 typo in one of UNOSAT's resource names — seen once, Cabo Verde listed as
both `FL20250812CPV` and `FL20250812COD`) is assigned one code: a checked
entry in `silver.CODE_OVERRIDES`, else the code of the most recently listed
resource version. Every listed code is carried on the processing rows as
`codes_listed`, so the choice is inspectable rather than implicit.

**Event code.** The resource-name code is the partition key (`code`). The
per-polygon `EventCode` attribute is recorded as `event_code_attr`; it is
more specific inside long monitoring activations (South Sudan's 2022 code
carries layers attributed to 2021 and 2022 sub-events) but is also wrong in
some SHP exports, so it never drives partitioning. Resources without a
parseable code (16 %, almost all XLSX) fall back to the layer attribute, then
to `HDX-{dataset_name}`, with `code_method` recorded.

**Layer grammar.** Tokenise on `_`. A leading `UNOSAT` token (2026 products:
`UNOSAT_Multisensor_20260826_20260828_FloodExtent`) is dropped. Sensor = the
next token, or its alphabetic prefix when fused with a date (`ST20180107`,
`RS20180209`, `L820180822`); `Multisensor(s)` → `multiple`;
`ST`/`ST1` → Sentinel-1, `ST2`/`ST3` → Sentinel-2/3, `PHR` → Pléiades, `PL`
→ Planet, `RS`/`RS2` → RADARSAT-2, `WV2`/`WV3` → WorldView. Dates = every
8-digit token that parses as a date (one → exact date; two → window; three
or more, as in multi-sensor names like `ST3_..._ST2_..._ICEYE_..._FloodExtent`
→ window from min to max and `sensor = multiple`); malformed tokens
(`0150118`, `201400819`) are recorded and not parsed. Kind = the first match
in the vocabulary below (order matters: `PreFlood` before `Flood`,
`MaximumFlood` before `Flood`). Everything else is area text. Unmatched
layers land in the processing ledger as `unclassified` with their names.
`aoi`/`areaofinterest` match a whole `_`-delimited token only: the coverage
rules sit ahead of the water rules, so substring matching filed every real
water layer carrying a numbered zone suffix
(`ST1_20191105_WaterExtent_BasseKotto_CAF_AOI1`) as a coverage footprint.

| name contains (casefolded) | table | role / `layer_kind` |
|---|---|---|
| `cloudobstruction` | coverage | `not_analysed` |
| `analysisextent`, `analysis_extent`, trailing `extent` alone (substring); `areaofinterest`, `aoi` (**whole token only**) | coverage | `footprint` |
| `permanentwater`, `prefloodwater`, `preflood`, `archivewater` | observed_event | `water_pre` |
| `maximumflood`, `maxflood`, `cumulative` | observed_event | `aggregate_max` |
| `minimumflood` | observed_event | `aggregate_min` |
| `floodextent`, `flood_water`, `floodwater`, `flood` | observed_event | `flood` (subject to per-polygon class) |
| `satellitedetectedsurfacewater*`, `satellitedetectedwater`, `waterextent`, `water` | observed_event | `water` (subject to per-polygon class) |
| `damage`, `structure`, `building`, `idp`, `shelter`, `landslide`, `road`, `bridge`, `harbour`, `health` | skipped, counted by name | |

**Per-polygon class.** From the resolved `Water_Class` text (GDB code →
`domains.parquet` for that layer's bound domain; SHP text as-is, or `d_*`
decoded columns when present):

| resolved text (either domain) | `layer_kind` |
|---|---|
| Preflood Water; Archive Water Extent / Pre-Flood Water; Permanent Water | `water_pre` |
| Flood Water | `flood` |
| Satellite Detected Water (class 4, older domain) | `water` |
| Flood-Affected Land / Possible Flood Water; Satellite Detected Water / Possible Saturated Soil; Possible Saturated, wet Soil; Probable Flash Flood-Affected Land | `flood_possible` |
| Aquaculture; Swamp / Marsh / Mangrove; Snow Cover; Tsunami-Affected Land | `other_water` |
| Maximum Flood Water Extent (Cumulative); Maximum Satellite Observed Water (Cumulative) | `aggregate_max` |

Precedence: the layer name decides `flood` vs `water` vs `water_pre` when the
polygon class is null or **unfilled** (an all-default record: class 0 with
sensor 0 and confidence 0 in a SHP, or all-null in the GDB; the corpus has
such layers), and `class_method` ∈ {`domain`, `text`, `decoded_column`,
`layer_name`} says which path was taken. A polygon whose class contradicts
its layer name (a `water_pre` class inside a `FloodExtent` layer) keeps the
polygon class and sets `class_conflict = true`. A code with no domain entry
(Confidence 0 is not in the Confidence domain) resolves to null with
`class_method = unresolved_code`, never to a guess.

**Canonical columns on `observed_event`** (names shared with CEMS silver):
`code`, `code_method`, `event_code_attr`, `target_ids` (list), `layer_name`,
`layer_kind`, `class_text`, `class_method`, `class_conflict`, `area_label`,
`sensor`, `sensor_raw`, `acq_datetime`, `acq_window_start`, `acq_window_end`,
`acq_precision` (`date` | `window`; UNOSAT never gives minutes),
`acq_method` (`attribute` from the per-polygon sensor date; `filename` when
only the layer name carries a date; `window` for composites), `acq_conflict`,
`water_status`, `confidence`, `field_validation`, `staff_id`, `notes`,
`geometry_source`, `source_crs`, `attrs_json` (everything raw, verbatim),
`geometry` (EPSG:4326).

Silver adds `sensor_method` ∈ {`filename`, `attribute`, `none`} next to
`sensor` on both `observed_event` and `coverage`. The layer name is
authoritative when it names a sensor; otherwise the per-polygon `Sensor_ID`
text is used, which carries sensors the filename grammar never sees
(COSMO-SkyMed, SkySat, SPOT, Kompsat). Without the column a consumer could
not tell the two apart, and `sensor_class` in gold would silently mix them.
The same resolution builds `sources.sensor`, so the tables agree.

**Acquisition.** Filename date(s) and the per-polygon sensor date are both
kept. Agreement (equal, or the attribute inside the filename window) gives
`acq_precision = date` (or `window` for composites) with `acq_conflict =
false`. Disagreement (6 % in the sample: month/day swaps, a few days' drift)
gives `acq_precision = window` spanning both values and `acq_conflict = true`,
so a consumer filtering to day precision drops them rather than receiving a
silently chosen date. A layer whose name carries a date window (a
composite) and whose polygons carry no sensor date is `acq_precision =
window`, `acq_method = window`; `acq_method = filename` is reserved for a
single filename date with no attribute date. Layers with no date anywhere
are `acq_precision = none` and excluded from gold.

`coverage`: `code`, `layer_name`, `role` (`footprint` | `not_analysed`),
`sensor`, `acq_*` as above, `attrs_json`, `geometry`. `sources`: one row per
distinct `(code, sensor, acq_datetime)` seen across layers.

Processing ledger `silver/_meta/processing.parquet`: one row per `(sha256,
layer)` — the resumable unit, one per encounter of a layer content rather
than one per content, so every zip that shipped it is accounted for —
`status` ∈ {`ok`, `unclassified`, `skipped_non_water`, `no_date`,
`unreadable`}, `geometry_source`, carrying `target_ids`, polygon counts by
`layer_kind`, `shp_gdb_mismatch`. Absence of water polygons in a layer is
`ok` with zero rows, never an error. A layer whose content was already
written under this code is `ok` with `reused = true` and no polygon counts:
the counts sit on the row that wrote the file.

## 4. Gold (`gold.py`) — schema v2, shared with CEMS

Grain: one row per `(label_source, code, area_label, acq_start, acq_end)`.
Per row up to three dissolved geometries and one valid mask:

| column | content |
|---|---|
| `geom_water` | dissolve of `water`, `water_pre`, `flood` (all water present at acquisition); null if none |
| `geom_flood` | dissolve of `flood`; null if not separable |
| `geom_possible` | dissolve of `flood_possible`; null if none |
| `geom_valid` | the matched `footprint` minus `not_analysed`; `valid_basis` ∈ {`footprint_minus_cloud`, `footprint`, `none`}, `valid_match` ∈ {`interval`, `product`} |

`aggregate_max`, `aggregate_min` and `other_water` never enter gold
geometries; their counts ride along. Rows with `acq_conflict = true` are kept
(they are `window` precision) so nothing is silently dropped.

`label_index.parquet` columns: `label_source` (`unosat` | `cems`), `code`,
`name`, `countries`, `aoi` (area label), `acq_start`, `acq_end`,
`width_days`, `label_day`, `acq_method`, `acq_precision`, `acq_conflict`,
`sensor`, `sensor_class` (`sar` | `optical_vhr` | `optical_hr` |
`optical_coarse` for VIIRS/MODIS | `multiple` | `unknown`), `sensor_gsd`
(null for UNOSAT), `det_methods` (null for UNOSAT), `product_classes`
(layer kinds present), `confidence`, `water_status`, `n_polygons`,
`water_area_km2`, `flood_area_km2`, `possible_area_km2`, `valid_basis`,
`valid_match`, `valid_area_km2`, `minx`, `miny`, `maxx`, `maxy`, `target_ids`,
`excluded_aggregate_n`. Areas in EPSG:6933 as CEMS gold does. `sensor_class`
exists because 1,829 of the label layers are VIIRS (375 m, automated), and a
consumer must be able to tier them differently from a Pléiades digitisation.

CEMS gold is rebuilt to v2 in a follow-up (`geom_flood` = today's `geometry`,
`geom_valid` = today's `valid_geometry`, `geom_water` null until the
hydrography extension lands, `label_source = cems`). Until then the fusion
reader accepts v1 by column presence and says which it got.

Rules settled while building it (Tasks 7-8), recorded here because they are
the difference between a missing label and a negative one:

- **`geom_flood` null vs empty.** Null where no layer in the set set out to
  map flood extent (a `WaterExtent` layer says "water here", not "flood
  here"); an **empty** geometry, area 0, where a flood-kind layer looked and
  its polygons all resolved to something else. Unknown and none are not the
  same claim.
- **Coverage is matched to a label set by source product and area**, following
  CEMS gold's `target_id` rule: a coverage row belongs to the set when it
  shares at least one `target_id` with it *and* carries the same area label.
  Measured against the real silver output (285 label sets, 185 footprint
  rows), exact `(area, interval)` matching gives a mask for 46 % of sets and
  interval overlap 51 %, against 73 % for product-and-area: a footprint layer
  usually carries only its filename's date while the observed layer's
  per-polygon sensor dates widen its interval, so two layers out of one
  product rarely share an interval exactly. `target_id` alone reaches 84 %,
  and the extra 11 points are one AOI's footprint masking another's — never
  matched across areas. The interval survives as a refinement, not a gate:
  `valid_match = "interval"` when the matched coverage also carried the
  identical `(acq_start, acq_end)`, `"product"` when the link was product and
  area alone, so a consumer can tier the two. `coverage` carries no
  `area_label` (§3's column list), so gold re-derives it from the layer name
  with the same grammar that produced the observed one.
- **A set built from more than one sensor is `sensor_class = "multiple"`.**
  `sensor` keeps the modal value for provenance, but classing a set built
  from a SAR pass and a VHR digitisation as `sar` would tell a consumer one
  thing about a label that is two. Both are taken over the rows that
  contributed geometry, never the excluded ones: a cumulative layer's
  instrument produced none of the label, and a set whose every row was an
  excluded kind has no sensor at all.
- **A label set whose every polygon was an excluded kind keeps its row**,
  with null geometries and `excluded_aggregate_n` set. Dropping it would
  erase the only record that those polygons existed.

Gold is written per code — `gold/labels/code={EventCode}/data.parquet` and
`gold/_index_parts/code={EventCode}.parquet` — and the whole
`label_index.parquet` is concatenated from *every* part in blob at the end of
each run, not from what that run rebuilt. That is what makes the stage
resumable per code without ever publishing an index that covers only part of
the corpus. An index part is mutable (rebuilding a code rewrites it in place),
so the mirror is trusted only when its size matches the blob listing's, and a
part that lacks any `label_index` column was written by an older schema and
raises rather than being reindexed into shape with nulls.

## 5. Audit (`audit.py`) and report

Same defect-fix loop as CEMS. Rules: **B1** no pending targets; **B2** blob
census equals ledger (sha256 set and sizes); **B3** every uploaded GDB has
domain rows or an explicit `no_domains` marker; **S1** processing ledger
covers every uploaded flood/cyclone resource version; **S2** every code with
water layers has `observed_event` and `coverage` partitions; **S3**
acquisition dates plausible (2005 ≤ year ≤ now) and within one year of the
event-code date; **S4** vocabularies within the documented sets; **S5**
`unclassified` share per code below a threshold, else listed; **S6** every
`gdb` row's SHP cross-check recorded where a SHP exists; **G1** every gold
row has `geom_valid` or `valid_basis = none`; **G2** no aggregate polygons
contribute to gold geometries. Exit 1 on failure; S/G failures land in the
stale-code list.

`report.py` renders a status page (counts by year, country, sensor class,
precision, kind) in the CEMS report template, plus a label-coverage map for
the fusion work (codes with `geom_water`, `geom_flood`, both).

## Fail-loud rules

Three states, never conflated: **upstream absence** (404, not-a-zip, dataset
without resources) → explicit ledger status; **fetch or upload failure** →
recorded, raised at the end of the run, retried only on request; **empty
content** (a water layer with zero polygons, a code with no water layers) →
`ok` rows with zero counts. No `try/except: continue`; workers raise, the
main thread records.

## Testing

Tests live under `tests/unosat/` (the repo's pytest `testpaths`), with library
code in `src/gie/unosat/` so it is importable. **Phase 1 (bronze) coverage is
in place**: event-code parsing, status vocabulary, per-host limiter, cache
atomicity and concurrency, ledger build and merge, harvest worker outcomes
(404, not-a-zip, untestable zip, network error, upload failure, lost race,
dedup), URL settlement and representatives, reconcile, journal, checkpoint,
domains parsing and crash-safe persistence, audit rules.

**Phase 2–3 (silver/gold) coverage is in place as well.** Done:

- layer grammar over the 2,600 distinct real names (the committed fixture
  `tests/unosat/fixtures/layer_names_flood.txt`) asserting the documented
  classification counts, with every unmatched name listed in the sibling
  fixture — `test_grammar.py::test_fixture_coverage_counts`;
- fused sensor-date tokens, multi-date names, malformed dates
  (`test_grammar.py`);
- `Water_Class` resolution for text, for a GDB code with a domain, for a code
  with no domain entry (resolves to null with method `unresolved_code`) and
  for unfilled records (falls back to the layer name) — `test_classes.py`;
- content deduplication, two ledger rows and one blob object
  (`test_silver.py::test_cli_skips_a_layer_whose_content_is_already_in_silver`);
- the acquisition cross-check in all five states — agree, in-window,
  disagree, filename-only, none (`test_acquisition.py`);
- reprojection from a non-4326 source CRS, and the raise when a populated
  layer carries none (`test_readers.py`);
- the gold dissolve with and without cloud obstruction, both `valid_basis`
  and both `valid_match` values, and the multi-geometry GeoParquet round-trip
  (`test_gold.py`).

Genuinely outstanding: **v1/v2 gold reader compatibility**, which belongs to
the fusion reader in `ds-flood-gfm` rather than to this repo and lands with
the CEMS rebuild to gold v2.

Fixtures are small synthetic shapefiles and trimmed `ogrinfo -json` dumps,
not the sampled zips.

## Phasing

1. Discovery + harvest + domains + audit B-rules. Harvest runs unattended
   (~22 GB of distinct content).
2. Silver + audit S-rules + processing ledger, GDB-first.
3. Gold v2 + report + audit G-rules; fusion reader in `ds-flood-gfm` updated.
4. Follow-ups, each its own ADR: CEMS gold v2 rebuild; CEMS hydrography
   extraction; unosat.org non-HDX products.

The grammar survey originally planned as phase 1 was done during design
(this revision); its outputs — the full member inventory and the classified
name list — become the test fixtures.

## ADRs to write with this work

- `0033-unosat-flood-archive-content-addressed-bronze.md` — HDX cumulative
  snapshots → sha256-keyed bronze; SHP+GDB both archived, GDB read first.
- `0034-flood-label-gold-v2-water-and-flood-geometries.md` — shared gold with
  `label_source`, `sensor_class` and separate water / flood / possible
  geometries; supersedes the gold section of ADR-0029.

## Open questions

- HDX `hash` on resources: is it a content hash usable to skip downloads on
  re-discovery? Cheap to test in phase 1 against our sha256.
- Rate limits on the CERN and unosat.org hosts: none observed at six
  workers reading central directories; full downloads may differ.
- Whether GPKG (1 resource) needs its own reader or is skipped with a status.
