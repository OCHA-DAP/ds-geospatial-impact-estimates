---
status: "accepted"
date: 2026-06-26
deciders: data science team
---

# Access Azure Blob directly with DuckDB + SAS, not the ocha-stratus loader

## Context and Problem Statement

The team's standard way to reach the Azure Blob lake is the internal
`ocha-stratus` package. Our hot path, however, is analytical: scan
pre-aggregated gold tables and large building-footprint GeoParquet to answer
"damage in admin unit X" style queries. We need to decide how this project
authenticates to and reads from Blob — and whether to use the standard package,
given a future maintainer will ask "why not ocha-stratus like everywhere else?".

## Decision Drivers

* Reads must be cloud-optimized: column/row-group pruning + HTTP range requests,
  not full-file downloads.
* Stay within the team's security-approved access (no new credentials/mechanism).
* Don't reinvent the canonical CODAB admin boundaries.
* Minimal moving parts for an emergency v1.

## Considered Options

1. **DuckDB azure extension reading GeoParquet directly, authenticated with the
   team SAS tokens** (`DSCI_AZ_BLOB_*`).
2. **ocha-stratus** (`load_parquet_from_blob`, etc.) for the query path.
3. **Managed identity / credential chain** instead of SAS.

## Decision Outcome

Chosen option: **Option 1**. DuckDB reads Parquet directly over the `azure`
extension, so a query reads only the row-groups/columns it needs instead of
downloading whole blobs. We reuse the existing `DSCI_AZ_BLOB_{STAGE}_SAS[_WRITE]`
tokens via a DuckDB azure secret (`CONNECTION_STRING` with
`SharedAccessSignature=…`), matching the working pattern already in
`ds-cholera-pdf-scraper`. No new secrets are provisioned.

`ocha-stratus` is **rejected for the query path** because its blob helpers
download the full blob into memory (`download_blob().readall()` →
`read_parquet(BytesIO(...))`), which defeats the point of cloud-native scanning
on large footprint/gold data. It remains fine for **one-time** tasks — notably
pulling the canonical CODAB boundaries into `bronze/` — where it never enters
the runtime query path.

Managed identity is **deferred**: the team uses SAS today and we keep it for
now. The auth is isolated in `gie.config`, so switching the secret to
`PROVIDER credential_chain` later is a one-function change.

### Consequences

* Good, because reads are cloud-optimized and v1 needs no new infrastructure.
* Good, because we stay on approved SAS credentials, shared with ocha-stratus.
* Bad, because SAS tokens expire and must be rotated; that operational burden is
  now ours, and a stale token surfaces as auth errors mid-query.
* Bad, because the SAS is interpolated into a `CREATE SECRET` statement
  (DuckDB does not bind parameters there); we keep it out of logs, but it is not
  as clean as managed identity, which is the eventual target.
* Neutral, because ocha-stratus stays a permitted tool for non-hot-path I/O.

## Pros and Cons of the Options

### Option 1 — DuckDB + SAS direct

* Good, because column/row-group pruning + range reads; no full downloads.
* Good, because reuses approved tokens and an in-team proven pattern.
* Bad, because SAS rotation/expiry is an operational cost.

### Option 2 — ocha-stratus for the query path

* Good, because it is the standard, already-approved package.
* Bad, because it downloads whole blobs into memory — wrong for large
  analytical scans.

### Option 3 — Managed identity now

* Good, because no token rotation; the cleaner long-term auth.
* Bad, because it diverges from current team practice and needs RBAC role
  assignments that would gate an emergency delivery.

## More Information

* In-team DuckDB-over-Blob precedent:
  `ds-cholera-pdf-scraper/src/cloud_logging/duckdb_cloud_query.py`
* ocha-stratus blob helpers: `ocha-stratus/src/ocha_stratus/azure_blob.py`
* Revisit auth (→ managed identity) when RBAC roles are assigned for the app
  service plan's managed identity; supersede the auth half of this ADR then.
