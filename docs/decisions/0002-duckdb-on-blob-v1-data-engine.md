---
status: "accepted"
date: 2026-06-26
deciders: data science team
---

# Use DuckDB over GeoParquet on Azure Blob as the v1 data engine; defer PostGIS

## Context and Problem Statement

We need an engine for both the ETL (bronze → silver → gold over the medallion
layout) and the read path for the viewer. The team's Azure environment offers
Blob storage, Postgres, Databricks, and an app service plan, and is
Python-majority. The work is emergency-first (ship in days) but is expected to
grow toward more events and global scale. What should the v1 store and engine
be, and when do we add heavier infrastructure?

## Decision Drivers

* Speed to a working v1; minimal infrastructure to stand up and secure.
* The viewer is read-mostly over **pre-aggregated** gold tables.
* Python-native; runnable on the existing app service plan.
* A clear, evidence-based trigger for when to escalate, not a guess.
* Keep the system-of-record in the lake (Blob), not in a serving database.

## Considered Options

1. **DuckDB (`spatial` + `azure` + `h3`) over GeoParquet on Azure Blob**, as
   both ETL and serving engine. No PostGIS in v1.
2. **PostGIS as the primary store and serving engine** from day one.
3. **Databricks + Apache Sedona** as the primary engine from day one.

## Decision Outcome

Chosen option: **Option 1**. DuckDB reads and writes Parquet directly on Azure
Blob via the `azure` extension (credential-chain auth, incl. managed identity),
does the spatial work via `spatial`, and indexes to H3 via the `h3` community
extension — verified to exist with extensive native functions. One process is
both ETL and read path, so v1 stands up with the fewest moving parts. Blob +
Parquet remains the system of record; DuckDB is a compute/serving layer over it,
not a separate source of truth.

PostGIS is **deferred, not rejected**. The team already has Postgres
provisioned, so adding it later is cheap; letting "we have it" pull it into v1
is the premature-infrastructure trap. Databricks + Sedona is the **platform
track** for global/multi-event scale and runs in parallel mainly as an
approvals/procurement effort — it should not gate the viewer.

**Escalation triggers — introduce PostGIS (and/or Sedona) when:**

* Multiple *processes* need concurrent write access to the same store (DuckDB's
  strength is a single read/write process; cross-process concurrency is where it
  breaks down).
* The viewer needs low-latency dynamic spatial queries that do **not** reduce to
  scanning a small pre-aggregated gold table.
* We want a tile server backed by live tables (e.g. `pg_tileserv` / Martin).
* Data outgrows comfortable single-node processing (→ Databricks + Sedona).

### Consequences

* Good, because v1 needs only Blob + a Python process on the app service plan.
* Good, because ETL and serving share one engine and one data format.
* Good, because the lake stays authoritative; the serving layer is disposable.
* Bad, because DuckDB is not built for many concurrent writers; we must not
  retrofit it into a transactional multi-writer role.
* Bad, because the `h3` extension is community-maintained (not core), a minor
  supply-chain/maintenance risk to track.
* Neutral, because for a public app we must keep gold tables small and
  pre-aggregated so reads stay snappy (a design constraint, not a blocker).

## Pros and Cons of the Options

### Option 1 — DuckDB over Blob

* Good, because fewest moving parts; reads/writes Parquet on Blob natively.
* Good, because the same engine and files serve ETL and the viewer.
* Good, because trivially portable (laptop ↔ app service plan ↔ Databricks).
* Bad, because single-writer; not a concurrent transactional store.

### Option 2 — PostGIS first

* Good, because mature concurrency, spatial indexes, tile-server ecosystem.
* Bad, because more infra to provision/secure for a read-mostly v1 that does not
  yet need any of it.
* Bad, because tempts us to make the serving DB the system of record.

### Option 3 — Databricks + Sedona first

* Good, because it is the right tool at global/multi-event scale.
* Bad, because heavy for a single city-scale event; cluster ops and approvals
  would gate an emergency delivery.

## More Information

* DuckDB Azure extension: https://duckdb.org/docs/stable/core_extensions/azure
* DuckDB h3 community extension:
  https://duckdb.org/community_extensions/extensions/h3
* DuckDB concurrency model:
  https://duckdb.org/docs/current/connect/concurrency
* Engine serves the harmonization model in `0001`.
* The rendering/shell choice (Streamlit + pydeck vs Panel/Solara + Lonboard) is
  a separate decision, pending a spike; an ADR will follow.
