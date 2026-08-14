---
status: "accepted"
date: 2026-08-14
deciders: data science team (zackarno)
---

# Event-keyed partitioning above country, with an in-repo event registry

## Context and Problem Statement

The data lake and viewer were built for one event (the Venezuela earthquake,
`adm0=VE`-keyed throughout). A second event — the Colombia earthquake — makes
country the wrong partition key: country is an **attribute of an event**, not
an identity. The same country can have repeat events, and a single event can
cross borders and arrive as one undivided delivery. Something has to become
the top-level key instead, and something has to say which events exist.

## Decision Drivers

* Country does not identify an event; it is not even always singular.
* Cross-border deliveries arrive as one file; splitting them at ingest to fit
  a country-keyed layout would violate ADR-0005's as-received bronze.
* No reader prunes by country today — the viewer reads a whole event.
* A run that forgets to name its event must fail loudly, never fall back to a
  shared or legacy layout.
* Minimal new infrastructure — an emergency-response codebase, one active
  maintainer.

## Considered Options

* `event=` partition above `source=`, country demoted to a column (chosen).
* Country-first: `adm0=` above `event=`.
* Per-event storage containers/prefixes (full isolation).
* Keep `adm0=` inside the event tree for new events.
* Registry: `events.yaml` in-repo.
* Registry: a Postgres event table.
* Registry: derive events from blob listing (no registry at all).

## Decision Outcome

Chosen: **`event=` as the first partition under every tier, country demoted
to a column**, with **`events.yaml`, checked into the repo, as the sole
registry**.

```
bronze/event=20260812-co-earthquake/source=copernicus_ems/code=EMSR9xx/...
gold/event=20260812-co-earthquake/model=common/...
platinum/event=20260812-co-earthquake/...
```

`gie.config.blob_path()` / `az_path()` — the choke point every pipeline
writes through — gain a **required, keyword-only `event` argument** with no
default. `event=None` is not an omission; it is the explicit opt-out for the
two cases that are not per-event: CODAB boundaries (a shared, country-keyed
reference tree, `bronze/source=codab/adm0=XX/`, reused across events with
nothing re-ingested) and the App Service's legacy pinned layout. Every other
pipeline gets a required `--event` CLI flag; a run that doesn't name its
event fails loudly instead of silently landing in the legacy tree.

The registry is `events.yaml` plus a loader (`gie.events`) that validates on
load — required fields, unique IDs, valid adm0 codes — and raises
`EventRegistryError` on anything invalid; `stage_serving`/`publish_events.py`
refuses to publish an invalid registry. Two events are registered today:
`20260624-ve-earthquake` and `20260810-co-earthquake`. The event slug
(`<yyyymmdd>-<countries>-<hazard>`) is a **mnemonic only** — no code parses
it; the registry's `countries` list and `hazard` field are the sole
authority for anything that reads those attributes.

### Rejected: country-first (`adm0=` above `event=`)

No reader prunes by country — the viewer reads per-event, and a column
filter is free in DuckDB/hyparquet, so pruning buys nothing a partition
wouldn't already give the actual access pattern. Worse, it breaks on the
case it exists to handle: a cross-border event straddles two country
partitions, forcing the as-received delivery to be split at ingest.

### Rejected: per-event storage containers/prefixes (full isolation)

Full isolation looks clean on paper but multiplies operational surface for
no reader benefit: every new event would need its own entry in the token
issuer's allow-list (ADR-0022) and its own pipeline configuration, rather
than one more value for an existing `--event` flag. Nothing reads across
containers today to justify the isolation.

### Rejected: keep `adm0=` inside the event tree for new events

This preserves the current path shape one level down
(`event=<id>/adm0=<XX>/...`) but re-creates the original problem: a
cross-border delivery still cannot be filed under two `adm0=` values without
splitting it, which violates ADR-0005's immutable-as-received bronze. Moving
the split from "before ingest" to "one level deeper" doesn't remove it.

### Rejected: Postgres event table

ADR-0002's Postgres-adoption trigger — a queryable, upsert-heavy,
concurrent-safe control-plane need — is not met by a handful of manually
registered events. `events.yaml` is also code-adjacent in the true sense:
registering an event and running its pipelines are the same act, done by the
same person in the same PR.

### Rejected: derive events from blob listing

Existence in blob storage is not the same claim as registration — a
half-written or abandoned prefix would silently become a "real" event with
no record of its onset date, countries, or external IDs, and nothing would
ever fail loudly when a listing was wrong. A registry that can't distinguish
"registered" from "some prefix happens to exist" is not a registry.

### Consequences

* Good, because a pipeline that omits `--event` fails immediately instead of
  writing into the shared or legacy tree by accident.
* Good, because a cross-border event is one path, not several, matching how
  it actually arrives and how the viewer actually reads it.
* Good, because CODAB is ingested once per country and reused across events.
* Bad, because every one of the ~113 existing call sites into
  `blob_path()`/`az_path()` had to be swept to pass `event=`.
* Bad, because the legacy un-evented tree cannot be deleted yet: the App
  Service's server-side DuckDB reads still point at it (§4 of the design
  spec pins it there), so deletion is **gated on the App Service retirement
  decision**, not on this migration finishing. This amends the design spec's
  §5 timeline, not the decision itself.
* Neutral, because the existing VE tree was migrated by a server-side blob
  **copy**, not a move — bronze 137 / silver 82 / gold 11 / platinum 70
  files, verified by count against the source tree — so nothing live loses
  its data mid-migration; the un-evented original is left in place until the
  gate above clears.

This **amends ADR-0005**: idempotent, immutable, versioned bronze paths are
unchanged in every respect except that they now sit one segment lower, under
`event=<id>/`. It does not supersede ADR-0005 — the idempotency model (unique
immutable keys, skip-if-present) is untouched.

## Pros and Cons of the Options

### `event=` above `source=`, country as a column (chosen)

* Good, because it matches the only read pattern that exists (per-event).
* Good, because cross-border deliveries need no special-casing.
* Bad, because it required a one-time sweep of every existing call site.

### Country-first (`adm0=` above `event=`)

* Good, because it matches the pre-existing (single-event) layout most
  closely, minimizing churn to the one call site that mattered before.
* Bad, because no reader prunes by country, so the partition buys nothing.
* Bad, because cross-border events force a split at ingest.

### Per-event containers/prefixes

* Good, because it gives the strongest possible isolation between events.
* Bad, because it multiplies the token-issuer allow-list and per-event
  pipeline configuration for isolation nothing currently needs.

### Keep `adm0=` inside the event tree

* Good, because within a single-country event, paths look unchanged.
* Bad, because it still splits cross-border deliveries, just one level down.

### `events.yaml` in-repo (chosen)

* Good, because registering an event and running its pipelines is already
  the same code-adjacent act.
* Good, because it validates on load and fails loudly, with no new infra.
* Bad, because it is not queryable and has no concurrent-write story — fine
  at the current scale of a handful of hand-registered events.

### Postgres event table

* Good, because it would be queryable and concurrency-safe.
* Bad, because ADR-0002's trigger for adopting Postgres is not met here.

### Derive events from blob listing

* Bad, because existence is not registration; nothing fails loudly when a
  listing is wrong, and no onset/countries/external-ID metadata exists to
  derive.

## More Information

* Design spec: `docs/superpowers/specs/2026-08-14-multi-event-foundation-design.md`
  (§2 registry, §3 partitioning, §4 VE migration, §5 legacy deprecation gate).
* Registry: `events.yaml`; loader and `EventRegistryError`: `src/gie/events.py`.
* Choke point: `Settings.blob_path()` / `Settings.az_path()` in
  `src/gie/config.py` (required keyword-only `event`).
* Registry publication to the viewer: `pipelines/publish_events.py` writes
  `events.json` to the platinum root, read by the SPA over the existing
  token-issuer path (ADR-0022) — no issuer change needed.
* Amends ADR-0005 (path scheme gains the event segment; idempotency model
  unchanged). Relates to ADR-0002 (Postgres-adoption trigger, not met),
  ADR-0014 (`platinum`/`platinum-prod` split, orthogonal and unchanged),
  ADR-0022 (token-issuer allow-list, a cost the per-event-container option
  would have multiplied).
* Revisit the legacy-tree deletion once the App Service retirement decision
  is taken (tracked separately; see `data_ledger.md` for the freeze/delete
  entry once recorded).
