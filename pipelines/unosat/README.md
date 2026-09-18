# UNOSAT archive harvester (bronze)

Archives every UNOSAT product resource catalogued on HDX (all hazards) into a
content-addressed bronze layer on blob, with a ledger that accounts for every
resource version: fetched, deduplicated, or explicitly unavailable upstream.
Design: `docs/superpowers/specs/2026-09-18-unosat-flood-archive-design.md`;
decision record: ADR-0033.

HDX is the catalogue, not the store: bytes come from unosat.org and CERN hosts.

```
global/unosat/bronze/blob={sha256}/{basename}     one object per distinct content
global/unosat/bronze/_meta/datasets.parquet        HDX dataset metadata
global/unosat/bronze/_meta/resources.parquet       THE LEDGER (one row per resource version)
global/unosat/bronze/_meta/zip_contents.parquet    member inventory per target
global/unosat/bronze/_meta/domains.parquet         (sha256, layer, field, domain, code, value)
global/unosat/bronze/_meta/domains_status.parquet  per-GDB: ok | no_domains | no_gdb_in_zip | gdb_unreadable
global/unosat/bronze/_meta/transfers.jsonl         append-only journal
```

## Run

```sh
uv run --group etl --group api python pipelines/unosat/discovery.py           # build/refresh ledger
uv run --group etl --group api python pipelines/unosat/harvest.py --dry-run   # preview
uv run --group etl --group api python pipelines/unosat/harvest.py             # transfer (resumable)
uv run --group etl --group api python pipelines/unosat/harvest.py --retry-failed
uv run --group etl --group api python pipelines/unosat/domains.py             # GDB domains
uv run --group etl --group api python pipelines/unosat/audit.py               # invariants
```

Needs `.env` with `DSCI_AZ_BLOB_DEV_SAS_WRITE` (via `gie.config`) and GDAL's
`ogrinfo` on PATH (`brew install gdal`). Default stage dev.

## Statuses

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

## Guarantees

Blob is truth: every run reconciles the ledger against a bronze listing.
Checkpoints every 25 transfers and on exit. Every attempt is journaled.
Re-running discovery is the backfill: new/re-published resources become
pending, vanished ones are flagged `missing_upstream`, never dropped.
Each distinct URL is downloaded once per run; ledger rows sharing a URL are
settled from the representative's outcome (journaled `via: url_sibling`).
