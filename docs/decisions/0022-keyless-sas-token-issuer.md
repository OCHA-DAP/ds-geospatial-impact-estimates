---
status: "accepted"
date: 2026-07-14
deciders: data science team (zackarno, with a colleague's SAS-minting guide)
---

# Keyless SAS token issuer as a standalone shared Azure Function

## Context and Problem Statement

The client-side serving model (ADR-0011) has browsers read PMTiles/Parquet directly from
blob storage, which requires handing the browser a credential. It must never be the storage
account key; it should be a short-lived, read-only, path-scoped **SAS**. Something
server-side must mint that SAS on demand. Three sub-questions: (a) account-key SAS vs
keyless user-delegation SAS; (b) where the minting endpoint is hosted; (c) whether it serves
one app or many.

Today the deployed viewer vends a **long-lived scoped SAS stored in an app setting**
(`GIE_PLATINUM_SAS`), rotated **by hand** — a recurring chore and a standing secret.

## Decision Drivers

* No long-lived secret stored anywhere (the account key least of all).
* Reusable across the team's client-side-blob apps, not one-off.
* Minimal, decoupled infrastructure — not bolted onto the App Service that ADR-0011 aims to retire.
* Least-privilege: read-only, directory-scoped tokens; per-app allow-list, no arbitrary-path minting.

## Considered Options

1. **Standalone Consumption Function App + managed identity, keyless user-delegation SAS** (this ADR).
2. **Token endpoint on the existing App Service + MI** — reuses the `_mint_scoped_sas` code and
   an already-running host; needs no new resource.
3. **Free Static Web App function + account-key mint** — mints rotating SAS on Free tier by
   storing the storage **account key** (Free SWA functions can't have a managed identity).
4. **Free SWA + static stored scoped SAS** — the current interim (manual refresh).

## Decision Outcome

Chosen: **Option 1.** A standalone `chd-ds-token-issuer` Function (Consumption/Linux/Python)
with a system-assigned managed identity mints **user-delegation SAS** — keyless, read-only,
directory-scoped, 24h. A config **allow-list** (`app` → account/folder) makes it a **shared
multi-app** issuer with no arbitrary-path minting. Verified 2026-07-14: `/api/token` returns
`mode: delegation-platinum` and the minted token range-reads a real blob (HTTP 206).

Option 2 was the runner-up and is cheaper (no new resource), but it **deepens dependence on
the App Service we intend to delete**, so the token would have to be relocated later. Option 3
stores the account **master key** in config (larger blast radius, and Free-tier can't use Key
Vault or MI to avoid it) — acceptable only as a dev stopgap. Option 4 is the manual-refresh
status quo we are replacing. All keyless options (1, 2) need the same one privileged grant:
`Storage Blob Data Reader` at **account scope** (required for `getUserDelegationKey`), which
only Owner/User-Access-Admin can assign — an IT step.

### Consequences

* Good: no stored secret; tokens auto-rotate; the manual `GIE_PLATINUM_SAS` refresh goes away
  for consumers pointed at the issuer.
* Good: shared/reusable — a new app is one allow-list entry (+ a role grant only if a new
  storage account); the issuer is the ADR-0011 Phase-3 "single token vendor" end-state, and it
  outlives the App Service.
* Good: negligible cost (Consumption; ~one call per page-load, not per tile).
* Bad: a new resource + its runtime storage account (`chd0tokenissuer`).
* Bad: deploy is fiddly here — `func` tools absent, Linux-Consumption `config-zip` skips pip
  (run-from-package) and OneDeploy is disabled — so deps are **vendored** and pushed via
  external run-from-package. Encapsulated in `token-issuer/deploy.sh`.
* Bad: the MI holds account-scope read on `imb0chd0dev`; least-privilege on *what browsers get*
  is preserved by minting directory-scoped tokens + the allow-list. Isolate sensitive data in a
  separate storage account (don't grant the issuer there) if that ever matters.

## More Information

* Code, usage, and deploy: `token-issuer/` (README + `deploy.sh`). Endpoint:
  `https://chd-ds-token-issuer.azurewebsites.net/api/token?app=<id>&tier=<staging|prod>`.
* Supports ADR-0011 Phase 3. Next: CORS + point the viewer/SWA client at the issuer, then
  retire the manual SAS for that consumer.
