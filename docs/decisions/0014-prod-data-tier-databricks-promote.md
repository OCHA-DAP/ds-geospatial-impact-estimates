---
status: "proposed"
date: 2026-07-02
deciders: zackarno
---

# Long-term prod/dev data split: prod on `imb0chd0prod`, promoted from Databricks

## Context and Problem Statement

The viewer runs a **cheap interim split** (2026-07-01): both App Service slots use
the single `imb0chd0dev` account; prod reads a `*-prod/` dir copy (`gold-prod`,
`platinum-prod`) that `pipelines/promote.py` writes from a laptop using the dev
account key; staging reads the working `gold`/`platinum`. It gated the CEMS + USGS
releases well, but it is a stopgap:

1. **No real isolation** — prod and dev share ONE storage account, so a dev-side
   problem (key rotation, quota, accidental delete, throttling) hits prod too.
2. **Promote uses the dev account KEY from a laptop** — a broad, long-lived
   credential we don't want to hold or rotate by hand.
3. **No versioning / rollback** — promote overwrites the published copy in place.
4. **The gold monolith collides** — `gold/model=common` (facts + building_flags)
   is one table code-coupled to `SOURCES` in `harmonize_common.py`; concurrent
   source work collides at gold, and promoting a collided dev-gold doesn't fix it.

Two facts point at the fix: (a) the **`imb0chd0prod` account exists and is idle**;
(b) the **prod-write credential (`DSCI_AZ_BLOB_PROD_SAS_WRITE`, `dsci` scope) is
already wired into Databricks and nowhere else** — deliberately, so prod can only
be written from a controlled place.

## Decision Drivers

* Real prod/dev isolation (separate accounts), not a shared-account dir split.
* Prod-write must run only where the prod credential lives (Databricks) — never a
  laptop or CI holding a broad prod key.
* A review gate **plus rollback** (versioned published data).
* Don't over-reach: keep the DuckDB-on-blob harmonize engine (ADR-0002) — the data
  has not outgrown single-node; Databricks is used only for its unique prod-write
  access, not as the compute engine.
* Fix the gold-monolith collision so new sources are incremental.

## Considered Options

1. **Keep the cheap same-account `-prod` dir split** (status-quo interim).
2. **Prod on `imb0chd0prod`, promoted from Databricks** (this ADR).
3. **Move the whole harmonize pipeline to Databricks** (compute + promote).

## Decision Outcome (proposed)

**Option 2.** The pieces:

* **Prod = `imb0chd0prod`.** The config already yields this: `account_name =
  {GIE_BLOB_ACCOUNT_PREFIX}{GIE_STAGE}`, so the prod slot runs **`GIE_STAGE=prod`**
  → reads `imb0chd0prod`. This **supersedes the interim `GIE_TIER`/`-prod`-dir
  mechanism**: the split moves from a dir suffix to a real account boundary. Dev +
  staging stay `GIE_STAGE=dev` → `imb0chd0dev`.
* **Databricks is the promoter, not the harmonizer.** Dev harmonize stays DuckDB
  (local/CI, on `imb0chd0dev`). A **Databricks job** reads the vetted dev
  `gold`/`platinum` and *copies* them to `imb0chd0prod` under a **dated version**
  (e.g. `…/gold/…/v=2026-07-02/`), using the prod-write credential it already
  holds. It copies vetted artifacts — it does **not** re-run the harmonization, so
  no logic is duplicated.
* **Versioned + rollback.** Each promote writes a new dated snapshot and updates a
  small `current.json` pointer (the live version). Prod resolves the pointer →
  the current snapshot. Rollback = repoint `current.json` at a prior version.
* **Gold decompose (enabling refactor).** Split `gold/model=common` into per-source
  partitions (`source=…`) + a cheap combine, removing the code-coupling +
  collision and making the promote per-source. Can land independently on dev first.
* **Prod auth + CORS.** The prod slot needs an `imb0chd0prod` read SAS (slot
  setting, per ADR-0007) or — better — MI + Storage Blob Data Reader on
  `imb0chd0prod`; CORS on `imb0chd0prod` for the client PMTiles; `/api/token`
  mints/serves the prod-account read credential.

Option 1 rejected long-term: no isolation, a laptop-held prod-adjacent key, no
rollback. Option 3 rejected: the harmonize runs comfortably single-node, so moving
it to Databricks is the premature-infrastructure trap ADR-0002 warns against —
Databricks earns its place here **only** for prod-write access.

### Consequences

* Good: true isolation; prod-write confined to Databricks; versioned publish with
  rollback; incremental new-source after the decompose.
* Good: minimal blast radius on compute — harmonize/DuckDB unchanged, still
  laptop-portable.
* Bad / cost: a new moving part (a Databricks job + its trigger/scheduling) and a
  second account to configure (CORS, auth, lifecycle). Each promote moves the data
  dev→prod (Databricks-side, not a laptop).
* Neutral: the interim `promote.py` / `GIE_TIER` mechanism is retired once this
  lands (kept briefly for transition).

## Open questions to investigate (on this branch)

1. **Databricks access shape** — confirm Databricks has dev-READ (`imb0chd0dev`)
   as well as prod-WRITE; confirm the `dsci` scope secret names and how one job
   authenticates to *both* accounts.
2. **Copy mechanism in Databricks** — Spark read/write vs `azcopy` vs the Azure
   SDK for the cross-account gold+platinum copy; HNS/ADLS-Gen2 caveats (we hit
   these in `promote.py`: server-side copy needs the dest dir pre-created; the
   DataLake API handles the nested-path creation on HNS).
3. **Versioning + pointer** — the `current.json` scheme and how prod resolves the
   current version (read on app start / per request; cache-busting on the client).
4. **Trigger** — how the promote job is kicked after staging review (manual
   Databricks run, parameterized job, or a CI→Databricks trigger) and who approves.
5. **Prod auth** — MI on `imb0chd0prod` (Storage Blob Data Reader) vs a slot-set
   read SAS; CORS config on `imb0chd0prod`.
6. **Gold decompose** — design the per-source gold + combine; sequence relative to
   the account move (decompose-first on dev is low-risk and independently useful).
7. **Cutover** — parallel-run period; move prod from the interim `-prod` dirs to
   `imb0chd0prod` without a gap.

## More Information

Supersedes the interim cheap split (handover 2026-07-01 / `promote.py` / `GIE_TIER`).
Does **not** supersede ADR-0002 (DuckDB stays the harmonize engine) or ADR-0007
(auth pattern — extends it to the prod account). Items 1, 2, 5 need Databricks /
Azure access to resolve; 3, 6 can be designed and prototyped on dev now.
