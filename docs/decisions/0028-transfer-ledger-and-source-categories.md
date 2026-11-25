---
status: "accepted"
date: 2026-08-15
deciders: data science team (zackarno)
---

# Per-file transfer ledger (repo JSONL) and reference-vs-analysis source categories

## Context and Problem Statement

`data_ledger.md` records what datasets exist in the lake at dataset granularity,
but nothing records the individual transfers: which exact file was downloaded
from which URL, when, with what checksum and size, under what licence, and where
it landed. When a provider re-uploads a resource under the same name, or a
product's provenance is questioned months later, there is no per-file audit
trail. Separately, the Colombia event splits sources by role: some are *not*
ML damage products (e.g. CEMS expert grading) and the viewer
will present them in a separate legend section — that role has to be recorded
somewhere at ingest time.

## Decision Drivers

* Every download/upload should leave one auditable record: origin URL, time,
  sha256, size, destination blob path, licence, provider, origin-system IDs.
* Idempotent loaders re-run on a cadence — re-runs must not spam the record.
* Same "minimal infrastructure now, portable to Postgres later" posture as
  `data_ledger.md` (ADR-0002's Postgres trigger still not met).
* The reference-vs-analysis role drives downstream behaviour (legend split,
  evaluation) and must be a validated value, not free text.

## Considered Options

* Append-only `data_transfers.jsonl` at the repo root, written by loaders
  through `gie.ledger.log_transfer()` (chosen).
* Extra columns on `data_ledger.md`.
* A transfer log in blob storage next to bronze (per-event JSONL or manifest
  blobs).
* A Postgres transfer table.

## Decision Outcome

Chosen: **`data_transfers.jsonl`, one JSON line per file landed, appended by
`gie.ledger.log_transfer()`**, with a validated `category` field
(`reference` | `analysis`, `gie.ledger.CATEGORIES`).

Each line carries: `ts` (UTC), `event`, `source`, `category`, `dataset`,
`provider`, `licence`, `origin_url`, `origin_meta` (origin-system identifiers:
HDX resource id / last_modified, CEMS activation + AOI + product version),
`size_bytes`, `sha256`, `blob_path`, `stage`. A re-logged transfer with the
same (`sha256`, `blob_path`) is skipped, so idempotent loader re-runs append
nothing. Git history gives the log tamper-evidence and review for free; JSONL
keeps it machine-readable and trivially loadable into DuckDB/Postgres later.

`category` is deliberately an enum validated at write time: it is the machine
record of the ground-truth-vs-ML split (CEMS expert grading is `reference`;
Microsoft and the SAR proxies are `analysis`), and the viewer
legend will key off it, so a typo must fail the loader, not silently create a
third category.

### Rejected: extra columns on `data_ledger.md`

The Markdown ledger is dataset-grained and upserted; transfers are file-grained
and append-only. Forcing per-file rows into the upsert table would either lose
history (upsert overwrites) or bloat the human-readable view into uselessness.
Two records, two shapes.

### Rejected: transfer log in blob storage

Blob appends are awkward (no atomic append on block blobs), the log would be
invisible in code review, and nothing machine-reads it from blob today. The
repo file keeps provenance next to the code that produced it, diffable in the
same PR that changed a loader. Portable to blob/Postgres when something
actually consumes it there.

### Rejected: Postgres transfer table

Same reasoning as ADR-0027's rejection of a Postgres event table: the
control-plane trigger (concurrent writers, queryable upserts) is not met by
single-operator, sequential ingest runs. The JSONL is designed to bulk-load
into Postgres unchanged if that changes.

### Consequences

* Good, because every bronze file now has an auditable origin (URL, checksum,
  licence) recoverable without touching blob storage.
* Good, because the reference/analysis role is captured at ingest, where the
  knowledge exists, instead of being retrofitted at viewer time.
* Bad, because loaders running concurrently could interleave appends; accepted
  while ingest is single-operator and sequential (same acceptance as
  `data_ledger.md`).
* Neutral: the log records what *this* tooling landed; files placed in blob by
  other means remain outside it (the blob layout stays the source of truth,
  ADR-0005).
