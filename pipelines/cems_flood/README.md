# CEMS flood historical archive harvester

Standalone module that archives **every Copernicus EMS Rapid Mapping flood
product zip (2012 → present)** to blob. Evidence and feasibility analysis:
`exploratory/0005-cems-flood-feasibility/`. Endpoint-by-endpoint provenance
and methods: [`ACQUISITION.md`](ACQUISITION.md).

This corpus is a general historical archive, **not** event-scoped project
data, so it lives outside the project prefix — container **`global`**:

```
global/copernicus_ems/flood/bronze/
  code=EMSR009/
    EMSR009_01MARIANNELUND_DELINEATION_DETAIL03-MONIT03_v1_vector.zip  ← byte-identical original
  code=EMSR927/
    EMSR927_AOI03_GRA_MONIT01_v1.zip
  _meta/
    activations.parquet    # all EMSR flood activations, both portals
    products.parquet       # THE ledger — one row per target incl. unavailable ones
    zip_contents.parquet   # one row per file inside every uploaded zip
    transfers.jsonl        # append-only attempt journal (every download/upload, incl. failures)
```

Partitioning is deliberately flat (`code=`/original basename): legacy
filenames span five naming generations, so parsing AOI/product/version into
path segments would be fragile — parsed metadata lives in `products.parquet`
where it can be fixed without moving blobs.

## Scope

Delineation, First Estimate and Grading vector zips (~2,900). Excluded, but
still inventoried in the ledger: Reference maps (`excluded_ref`), map
PDFs/JPGs (not listed — vector packages only), `EMSN*` Risk & Recovery
products. Known-unavailable targets carry explicit statuses:
`unavailable_not_migrated` (legacy pages the portal lost),
`unavailable_no_products`, `unavailable_status_N` (closed without delivery),
`unavailable_no_url`.

## Running

```sh
uv run --group etl --group api python pipelines/cems_flood/discovery.py            # build/refresh ledger
uv run --group etl --group api python pipelines/cems_flood/harvest.py --dry-run    # see what would transfer
uv run --group etl --group api python pipelines/cems_flood/harvest.py --limit 20   # shakedown
uv run --group etl --group api python pipelines/cems_flood/harvest.py              # full crawl (hours)
uv run --group etl --group api python pipelines/cems_flood/harvest.py --retry-failed
```

Needs the repo's `.env` (`DSCI_AZ_BLOB_*_SAS_WRITE`, via `gie.config`).
Default stage is `dev`; `--stage prod` when promoting.

## Resume / backfill semantics

- **Blob existence is the source of truth** (same idempotency model as
  `ingest_cems.py` / ADR-0005). Every harvest run first reconciles the ledger
  against a blob listing: already-uploaded targets are skipped, and ledger
  rows claiming `uploaded` whose blob is missing are demoted to pending with
  a warning. A killed run (Ctrl-C included — checkpoint runs in `finally`)
  loses at most the in-flight file.
- **Re-running `discovery.py` is the backfill**: fresh discovery merges onto
  the existing ledger — transfer outcomes are preserved, new activations /
  monitoring updates become `pending`, previously-unavailable targets that
  appear upstream become `pending`, and targets that vanish upstream are kept
  and flagged `missing_upstream`, never dropped.
- Failures are never retried silently: they stay visible in the ledger
  (`failed_download` / `failed_upload`, with HTTP status + error) until an
  explicit `--retry-failed`.

## Integrity & transparency guarantees

Per uploaded zip: HTTP status checked, zip integrity verified
(`ZipFile.testzip`), member inventory recorded to `zip_contents.parquet`
**during** download, `sha256` + size recorded, post-upload size verified
against the blob. Every attempt (success or failure) appends a record to
`transfers.jsonl` in this repo's `data_transfers.jsonl` field shape.

## Design decisions

- Full zips, not selective range-extraction: the whole corpus is ~15–25 GB
  (trivial storage) and the 7 `unavailable_not_migrated` activations prove
  CEMS history disappears — the raw zip is the insurance.
- Reuses this repo's machinery (`gie.config` credentials pointed at the
  `global` container, `gie.blobio` tuned uploads, ledger record shape) while
  staying structurally standalone: nothing here is wired into `run_all.py`
  or the event-keyed pipelines.
- `ocha-stratus` is used for reads/listing; **uploads go through
  `gie.blobio`** because stratus's plain-SDK upload path is the documented
  single-PUT timeout failure on this lake (see `src/gie/blobio.py` — measured
  ~8× slower and timeout-prone; same reason `ingest_cems.py` bypasses
  `to_blob`).
- Transfers run in a small thread pool (`--workers`, default 6): workers do
  pure download→verify→upload; the ledger, journal and checkpoints are
  main-thread only. Worker count is the politeness knob.
