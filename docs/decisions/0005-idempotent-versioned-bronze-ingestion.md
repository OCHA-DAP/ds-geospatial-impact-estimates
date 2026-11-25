---
status: "accepted"
date: 2026-06-26
deciders: data science team
---

# Idempotent, versioned bronze for piecemeal product ingestion; defer a Postgres ledger

## Context and Problem Statement

Damage products do not arrive as a single drop — they trickle in and get
revised. The first Copernicus EMS activation (EMSR884, "Earthquake in
Venezuela") makes this concrete: 15 products across 13 AOIs, only 4 delivered on
first poll, the rest with `expected_delivery` over the next 1–2 days; products
carry `version_number` and `monitoring_number` (later monitoring updates
supersede earlier grades); and the activation stays **open** until closed, so we
re-poll over time. Future sources will behave similarly.

We need ingestion that is **safe to run repeatedly**: it must pick up only
new/changed products, never overwrite or duplicate, and preserve every version
as an audit trail — without yet committing to a full ingestion framework.

## Decision Drivers

* Re-runnable / idempotent polling of an open, incrementally-delivered source.
* Immutable bronze: every product version kept as received.
* Minimal new infrastructure for an emergency timeline.
* A clear, non-premature trigger for when to add heavier machinery.

## Considered Options

1. **Blob-native idempotency**: version-encoded immutable bronze paths +
   skip-if-present existence checks + timestamped manifest snapshots. No ledger DB.
2. **Postgres ingestion ledger**: a mutable, upsertable catalog of every product
   version and its status, queried/updated each poll.
3. **Full source-adapter + runner framework** up front (with the ledger).

## Decision Outcome

Chosen option: **Option 1, now** — and Option 2 is the documented next step, not
a rejection.

Idempotency comes from the **path**: each product version lands at a unique,
immutable key, so re-polls skip what already exists and new versions coexist
with old ones:
```
bronze/source=copernicus_ems/code=EMSR884/aoi=02/product_type=GRA/v1_m0/EMSR884_AOI02_GRA_PRODUCT_v1.zip
```
A skip-if-present check (blob exists → don't re-download) makes the loader safe
to run on any cadence. A **timestamped product manifest** snapshot per poll
(`products_<last_update>.parquet`) records activation state and gives history for
free, without a database.

**Why defer the Postgres ledger.** A ledger is mutable, upsert-heavy,
concurrent-safe state — the right home for which is Postgres (this is precisely
the trigger ADR-0002 named for adopting it, and it is a *control-plane* use, not
geospatial serving). But for a **single source** polled by a **single** process,
blob-native idempotency already delivers safe re-runs; the ledger's real value
(cross-source "what's pending" queries, explicit supersession, a downstream
reprocessing signal, concurrent scheduled pollers) only materializes once we
unify multiple polled sources. Building it now would be guessing at that shape.

### Consequences

* Good, because polling is idempotent today with zero new infrastructure.
* Good, because bronze stays immutable and fully versioned (audit trail).
* Good, because the deferral has a concrete trigger, not "someday".
* Bad, because there is no queryable cross-source view of pending/ingested state.
* Bad, because supersession is *implicit* (a newer version is just a new path;
  downstream must choose the latest) rather than tracked.
* Neutral, because manifest snapshots in bronze are metadata, not raw product
  data, but are kept immutable (timestamped) to respect the bronze contract.

Amended by ADR-0027: paths gain a leading event=<id> segment; the idempotency model is unchanged.

## Pros and Cons of the Options

### Option 1 — blob-native idempotency

* Good, because no new infra; immutable, versioned, re-runnable immediately.
* Bad, because state is implicit in the blob layout, not queryable.

### Option 2 — Postgres ledger

* Good, because queryable, explicit supersession, concurrency-safe, a clean
  trigger for downstream silver/gold reprocessing.
* Bad, because premature for one single-process source; adds infra to operate.

### Option 3 — full adapter/runner framework now

* Good, because it is where this is heading as sources multiply.
* Bad, because building the abstraction before a second *polled* source defines
  its real shape risks over-fitting to CEMS.

## More Information

* CEMS access via `ocha-lens` `cems` (pinned to PR #49); loader:
  `pipelines/ingest_cems.py`.
* Revisit (→ adopt the Postgres ledger, superseding this deferral) when: a second
  polled source is added under a shared runner, polling moves to a schedule, or
  we need supersession/queryable ingestion state. Ties to the ADR-0002 triggers.
* Note: the team Postgres is **shared infrastructure**, so adopting it for a
  ledger is gated on team coordination, not just the technical trigger above —
  another reason the blob-native path is the right way to keep building now.
