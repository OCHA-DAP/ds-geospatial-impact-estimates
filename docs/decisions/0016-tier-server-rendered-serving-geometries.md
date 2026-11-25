---
status: "accepted"
date: 2026-07-02
deciders: zackarno
---

# Tier the server-rendered serving geometries via gold (close the silver leak)

## Context and Problem Statement

The cheap prod/dev split (ADR-0014) tiers only `gold`/`platinum`; `bronze`/`silver`
are a single shared copy. But a few layers are still **server-rendered** — the
FastAPI reads blob itself (with the app's broad `DSCI_AZ_BLOB_*` credential, *not*
the browser's platinum-scoped SAS) and returns GeoJSON. Two of those read
**silver**:

- `/api/extent` → `load_source_extent` → `silver/source=*/analysed_extent.parquet`
- `/api/coverage_detail` → `load_coverage_detail` → `silver/.../coverage_detail.parquet`

Because silver is shared and untiered, a dev harmonize instantly changes prod for
these layers — with **no promote and no approval**. This is exactly how the IMPACT
v2 AOI outline appeared on prod while the numbers were still v1 (observed
2026-07-02). It is a real gap in the publish gate.

(`/api/native` also has silver branches, but for impact/OSU it returns empty and
its MS/CEMS branches are unreachable — the client serves those as PMTiles. So it is
a latent path, not an active leak.)

## Decision Drivers

* Close the leak: nothing the app renders should bypass the promote gate.
* Small, low-risk, shippable now — a security/consistency fix shouldn't wait on a
  larger re-architecture.

## Considered Options

* **A. Tier the reads via gold.** Stage the served geometries into `gold/…/serving/`
  and point the loaders there — `az_path("gold")` → `gold-prod` on the prod slot, so
  reads become promote-gated. Keeps the server-rendered architecture.
* **B. Full client-side migration.** Convert extent/coverage (and impact/OSU native)
  to platinum PMTiles like native-MS/CEMS/HOT, flip the client registry
  `deckgl → pmtiles`, and retire `/api/extent`, `/api/native`, `/api/coverage_detail`
  so nothing is server-rendered at all.

## Decision Outcome

Chosen: **A**. It fully closes the leak (the actual bug) with a new `stage_serving.py`
step (copies per-source `analysed_extent` + CEMS `coverage_detail` from silver into
`gold/model=common/adm0=VE/serving/`) plus two one-line loader path changes
(`silver → gold`). `promote.py` already copies all of gold, so these publish only on
promote. Runs after the harmonizers, before promote (added to `run_all.py`).

### Consequences

* Good: the leak is closed with minimal surface; prod for these layers now changes
  only on promote, like the rest of the served tier. Low regression risk.
* Neutral: the layers stay **server-rendered** (the API still renders GeoJSON), and
  a small geometry copy now lives in gold (duplicated from silver). Gold is a fine
  home — it is tiered and promote-gated.
* Ordering: the `serving.py` change is code (deploys) and the `gold/serving/` data is
  produced by `stage_serving`. Data must exist before the code reads it — run
  `stage_serving` (+ promote for prod) before/with the deploy, or the loaders 404.

## Deferred (pushed down the road) — decisions NOT made here

* **B (full client-side migration).** The cleaner end state — everything served from
  platinum via the scoped SAS, no server-rendered endpoints — is left as v2-serving
  completion (with the agreement/H3 layers, per ADR-0011). It's larger frontend +
  pipeline work and shouldn't gate this fix. (Also: impact/OSU native have no vector
  geometry today; B would need to source it.)
* **Latent `load_native` silver branches.** Left as-is (unreachable via the client).
  B retires them; until then they remain a dormant server-side silver read.
* **`build_platinum` L89 hardcoded `platinum/values` path** — a separate
  promote-correctness bug, not addressed here.
