# UNOSAT archive: bronze, silver, gold

Archives every UNOSAT product resource catalogued on HDX (all hazards) into a
content-addressed bronze layer on blob, with a ledger that accounts for every
resource version: fetched, deduplicated, or explicitly unavailable upstream;
normalises the flood and cyclone ones into silver polygon tables; and dissolves
those into the shared flood-label gold schema the fusion work reads alongside
the CEMS archive. Design:
`docs/superpowers/specs/2026-09-18-unosat-flood-archive-design.md`; decision
records: ADR-0033 (bronze), ADR-0034 (gold v2).

HDX is the catalogue, not the store: bytes come from unosat.org and CERN hosts.

```
global/unosat/bronze/blob={sha256}/{basename}     one object per distinct content
global/unosat/bronze/_meta/datasets.parquet        HDX dataset metadata
global/unosat/bronze/_meta/resources.parquet       THE LEDGER (one row per resource version)
global/unosat/bronze/_meta/zip_contents.parquet    member inventory per target
global/unosat/bronze/_meta/domains.parquet         (sha256, layer, field, domain, code, value)
global/unosat/bronze/_meta/domains_status.parquet  per-GDB: ok | no_domains | no_gdb_in_zip | gdb_unreadable | zip_unreadable
global/unosat/bronze/_meta/transfers.jsonl         append-only journal
global/unosat/silver/_meta/layers.parquet          (sha256, zip_basename, source, layer, geometry_type, feature_count, fields, field_domains)
global/unosat/silver/_meta/layers_status.parquet   per-zip: ok | no_layers | gdb_unreadable | zip_unreadable | missing_from_inventory
global/unosat/silver/_meta/processing.parquet      THE SILVER LEDGER (one row per (sha256, layer) encounter)
global/unosat/silver/observed_event/code={EventCode}/layer={hash}-{name8}.parquet  water polygons
global/unosat/silver/coverage/code={EventCode}/layer={hash}-{name8}.parquet        footprints and cloud
global/unosat/silver/sources/code={EventCode}/data.parquet                         per-code (sensor, acquisition) summary
global/unosat/gold/labels/code={EventCode}/data.parquet    label sets, four geometry columns
global/unosat/gold/_index_parts/code={EventCode}.parquet   that one code's index rows
global/unosat/gold/label_index.parquet                     the whole catalog, NO geometry
```

`missing_from_inventory`: an uploaded SHP sha256 with zero rows in
`zip_contents.parquet` — reachable when harvest's `failed_upload` branch
recorded the ledger outcome without member rows and a later reconcile flipped
it to `uploaded` without re-inspecting the zip. Recorded, never raised.

## Run

```sh
uv run --group etl --group api python pipelines/unosat/discovery.py           # build/refresh ledger
uv run --group etl --group api python pipelines/unosat/harvest.py --dry-run   # preview
uv run --group etl --group api python pipelines/unosat/harvest.py             # transfer (resumable)
uv run --group etl --group api python pipelines/unosat/harvest.py --retry-failed
uv run --group etl --group api python pipelines/unosat/domains.py             # GDB domains
uv run --group etl --group api python pipelines/unosat/layers.py              # layer inventory (silver)
uv run --group etl --group api python pipelines/unosat/silver.py              # normalised polygons
uv run --group etl --group api python pipelines/unosat/gold.py                # label sets + label_index
uv run --group etl --group api python pipelines/unosat/audit.py               # invariants (bronze+silver+gold)
uv run --group etl --group api python pipelines/unosat/audit.py --silver      # silver only (S1-S7)
uv run --group etl --group api python pipelines/unosat/audit.py --gold       # gold only (G1-G2)
```

Needs `.env` with `DSCI_AZ_BLOB_DEV_SAS_WRITE` (via `gie.config`) and GDAL's
`ogrinfo` on PATH (`brew install gdal`). Default stage dev. The work dir
(ledger, journal, checkpoints) defaults to `$GIE_WORK_DIR` or
`platformdirs.user_data_dir("gie")/unosat_archive`.

`harvest.py` flags: `--scope`, `--limit`, `--workers` (default 6), `--per-host`
(default 3), `--sleep`, `--no-cache`, `--dry-run`, `--retry-failed`; the full
run used `--workers 8 --per-host 6`.

## Bronze statuses

| status | meaning | retried? |
|---|---|---|
| pending | has URL, will be fetched | — |
| excluded_format | non-archived format (KMZ, PDF, KML), inventoried only | never |
| uploaded | transferred and size-verified | — |
| uploaded_dedup | identical content already in bronze; ledger points at it | — |
| uploaded_untested | valid zip archived but members could not be test-decompressed (unsupported compression); error column says so | — |
| failed_download / failed_upload | our side or transient upstream | `--retry-failed` |
| unavailable_404 | upstream says gone (stable across hours) | never |
| corrupt_upstream | HTTP 200 but not a zip | never |

A lost upload race to an identical content path — another worker or run
already wrote that `sha256` first — is recorded as `uploaded_dedup`, not a
failure; it is never retried.

## Local cache

Downloads are kept at `$GIE_CACHE_DIR` (default `platformdirs.user_cache_dir("gie")`)
mirroring the bronze layout, so silver reads them without re-downloading.
Content-addressed, therefore never stale; delete freely. `--no-cache` disables.

## Silver

Reads bronze only, and writes one GeoParquet **per distinct layer content
under its name** — `(code, content_hash, layer_name)` — into two tables:
`observed_event` (water polygons) and `coverage` (analysis footprints and
cloud). `sources` is a small per-code summary of the (sensor, acquisition)
pairs its layers resolved to.

**GDB first.** Where a dataset ships both a geodatabase and shapefiles, the
GDB is read and the SHP is used only to cross-check layer names and decoded
text; disagreements land on the processing rows as `shp_gdb_mismatch`, and
`sibling_status` says when the check could not be made at all. The **layer
inventory** decides which a zip is, not HDX's `format` label, which is wrong
for some resources — the disagreement rides along as `format_label` /
`format_mismatch` rather than being quietly corrected.

**Idempotent by file name.** The file key is the content hash plus a short
digest of the layer name, so a layer re-shipped identically across 35 HDX zips
is written once and every later encounter is a path-exists skip recorded `ok`
with `reused=True`. The layer name is part of the key on purpose: two
differently-named layers legitimately carry identical geometry (one analysis
footprint shipped for two acquisition dates), and keying on content alone
dropped the second.

`silver.py` flags: `--codes`, `--limit`, `--workers` (default 3; zips are
processed in worker processes, `1` runs them in-process), `--force` (revisit
layers already in the ledger; files that exist are still not rewritten — this
is how a code's `sources` table is rebuilt after a partial run).

### `processing.parquet` statuses

One row per `(sha256, layer)` — per *encounter* of a layer content, so every
zip that shipped it is accounted for.

| status | meaning |
|---|---|
| ok | read and written (or reused); a layer with zero polygons is `ok` with zero rows, never an error |
| unclassified | the grammar could not classify the layer name; the name is recorded |
| skipped_non_water | a non-water layer by name (damage, structures, IDP…), a non-polygonal layer, or a GDB coded-value lookup table |
| no_date | no date anywhere; rows are kept with `acq_precision = "none"` and gold excludes them on that |
| unreadable | GDAL failed on that one layer; recorded with its error text, the run continues |

The `uploaded` flag says whether that file's push to blob is confirmed; null
means a ledger written before the flag existed and is reconciled against the
blob listing, never assumed either way.

## Local mirror (silver and gold)

`silver.py` writes every layer file to `{work_dir}/silver/…` first — the same
relative layout as `unosat/silver/` — and uploads it from there in the
background (6 threads, 60 s socket timeout, against bronze's 300 s: these are
tens-of-KB files, and one stalled socket must not halt the run). The
processing ledger's `uploaded` flag says whether the push is confirmed; a
checkpoint drains in-flight uploads before persisting, so a killed run leaves
`uploaded=False` rows whose files are already built and only need pushing —
the next run does that without re-reading a single zip.

`gold.py` mirrors the same way under `{work_dir}/gold/…`.

**The mirror is disposable; blob is truth.** Delete `{work_dir}/silver/` or
`{work_dir}/gold/` whenever you like: gold reads through
`silver.iter_layer_files`, which fetches back whatever the mirror lacks. The
blob **listing** decides what a partition holds, in both directions — a mirror
file no listing names is a leftover from an interrupted run and is never read,
so a build cannot depend on which machine ran it. Silver layer files are
content-addressed and therefore immutable, so a mirrored copy is trusted on
sight; a gold `_index_parts` file is rewritten in place when its code is
rebuilt, so its mirrored copy is trusted only when its size matches the
listing's.

**Read these files with the helpers, not a bare `geopandas.read_parquet`.**
Both a silver layer file and a gold labels file sit under a
`code={EventCode}/` directory *and* carry a `code` column, and pyarrow's
hive-partition inference then refuses to merge the two
(`ArrowTypeError: Field code has incompatible types`). Use
`silver.read_layer_file(path)` and `gold.read_labels_file(path)`, which turn
that inference off.

## Gold

Reads silver only. Per event code it concatenates every layer file of the
`observed_event` and `coverage` partitions and dissolves them into **label
sets**: one row per `(label_source, code, area_label, acquisition interval)`,
which is the shape a training-data reader wants — rasterise the geometries,
rasterise the mask, treat everything outside the mask as unobserved rather
than dry. Schema v2, shared with the CEMS archive (ADR-0034), so one reader
serves both corpora.

**Four geometry columns** on `labels/code=…/data.parquet` (primary
`geom_water`):

| column | content |
|---|---|
| `geom_water` | dissolve of `water`, `water_pre`, `flood` — everything wet at acquisition, the target comparable across sensors |
| `geom_flood` | dissolve of `flood`. **Null** where no layer set out to map flood extent (a `WaterExtent` layer says "water here", not "flood here"); an **empty** geometry, area 0, where a flood layer looked and found none |
| `geom_possible` | dissolve of `flood_possible` — possible flood-affected land, a different claim from observed water |
| `geom_valid` | the matched analysis footprint minus what was not analysed |

`aggregate_max`, `aggregate_min` (cumulative extents, not a snapshot) and
`other_water` (aquaculture, swamp, snow) never enter a geometry; they are
counted per label set in `excluded_aggregate_n`.

**The valid mask.** Coverage belongs to a label set when it shares at least
one `target_id` with it (the same source product — CEMS gold's rule) **and**
carries the same area label. Area is never crossed: a neighbouring AOI's
footprint would call unobserved ground observed. Two columns describe the
result, and both matter when filtering:

- `valid_basis` ∈ `footprint_minus_cloud` | `footprint` | `none`. `none`
  means no footprint matched — the honest answer, not a mask to invent.
- `valid_match` ∈ `interval` | `product` (null when there is no mask): whether
  the matched coverage also carried the identical `(acq_start, acq_end)`, or
  was linked by product and area alone. The interval is a refinement, not a
  gate — a footprint layer usually carries only its filename's date while the
  observed layer's per-polygon sensor dates widen its interval, so demanding
  equal intervals leaves most real label sets with no mask at all.

**`sensor_class`** ∈ `sar` | `optical_vhr` | `optical_hr` | `optical_coarse`
(VIIRS/MODIS) | `multiple` | `unknown`, so a 375 m automated product can be
tiered apart from a Pléiades digitisation. `multiple` whenever the contributing
rows carry more than one distinct sensor. Both `sensor` and `sensor_class`
describe the rows that produced the geometries, so an excluded cumulative
layer never lends its instrument to a label it did not produce.

**Resumable per code.** A code counts as built only when *both* its
`labels/` and `_index_parts/` files are in blob, and built codes are skipped
(`--force` rebuilds them). `label_index.parquet` is concatenated at the end of
*every* run from every part in blob — not from what that run rebuilt — so a
resumed or `--limit`ed run never publishes an index covering part of the
corpus. A part missing any `label_index` column was written by an older schema
and raises naming the file, rather than being reindexed into shape with nulls.
One code that cannot be built stops the run: everything already built is
skipped on the rerun, and an index assembled around a code that silently
failed is worse than no index.

`gold.py` flags: `--codes`, `--limit`, `--force`.

## Audit

`audit.py` flags: `--silver` (only S1-S7), `--gold` (only G1-G2); with
neither, all three sections run. A section whose inputs are missing (no
`processing.parquet`/`layers.parquet` yet, no `label_index.parquet` yet, a
gold code whose silver partition is not cached locally) prints `[SKIP]` with
the reason and counts against the exit code — it is never rendered as a pass.
Writes `audit_stale_codes.txt` (every code touched by a failing rule, the
defect-fix loop's reprocessing list).

| rule | checks |
|---|---|
| B1 | no pending targets left in the bronze ledger |
| B2 | blob census matches the ledger, both directions (paths + sizes) |
| B3 | every uploaded GDB has a domains status |
| S1 | processing covers every `(sha256, layer)` the silver selector chose |
| S2 | every code with an `ok` layer has its `observed_event`/`coverage` partition |
| S3 | acquisition dates fall in `[2005, now]` and within a year of their event code's date |
| S4 | `layer_kind`/`role`/`status`/`geometry_source`/`acq_precision` stay within their documented vocabularies |
| S5 | `unclassified` share per code is at most 4% |
| S6 | `shp_gdb_mismatch`/`sibling_status` are recorded consistently |
| S7 | every layer file the ledger says it built is confirmed uploaded |
| G1 | every gold label set has `geom_valid` or is explicit that it has none |
| G2 | `excluded_aggregate_n` matches the actual count of excluded-kind polygons in silver |

`format_mismatch` (an HDX `format` label disagreeing with what the zip turned
out to be) and content listed under more than one event code (`codes_listed`)
are reported alongside the S-rules, not failed — they are real properties of
the archive, not defects. S4 does not check `class_method`/`acq_method`:
those are per-polygon columns that live only in the raw silver files, and
checking them would mean reading every layer in the corpus for this one rule.

## Guarantees

Blob is truth: every run reconciles the ledger against a bronze listing.
Checkpoints every 25 transfers and on exit. Every attempt is journaled.
Re-running discovery is the backfill: new/re-published resources become
pending, vanished ones are flagged `missing_upstream`, never dropped.
Each distinct (URL, declared size) is downloaded once per run; ledger rows
with the same URL and declared size are settled from the representative's
outcome; an unknown declared size only matches another unknown size.
The settle step (rows whose URL is already uploaded) runs on the whole
ledger before `--scope`/`--limit` filtering, so a scoped run may settle rows
outside its scope.
Uploads pass the whole file through memory (`gie.blobio.upload` takes bytes);
peak RSS ≈ workers × largest file (337 MB in this corpus).
A missing work dir is restored from the blob `_meta/` copy before anything
runs, so losing the local files (reboot, new machine) costs nothing; the blob
copy lags the local one by at most one checkpoint (25 transfers).
